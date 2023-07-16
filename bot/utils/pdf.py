import os
import zipfile

from io import BytesIO
from pathlib import Path

import fitz
import img2pdf
from fpdf import FPDF
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def get_path(path: Path) -> Path:
    if not isinstance(path, Path):
        path = Path(path)
    return path


def get_image_size(img_path: str) -> tuple[int, int]:
    with Image.open(img_path) as image:
        return image.size


def convert_img(path: Path) -> Image.Image:
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def pil_image(path: Path) -> tuple[BytesIO, int, int]:
    img = convert_img(path)
    width, height = img.width, img.height
    membuf = BytesIO()
    img.save(membuf, format="JPEG")
    img.close()
    return membuf, width, height


def unicode_to_latin1(s: str) -> str:
    # Substitute characters
    s = s.replace("\u2019", "\x92").replace("\u201d", "\x94").replace("\u2013", "\x96")
    # Remove all other non-latin1 characters
    s = s.encode("latin1", "replace").decode("latin1")
    return s


def fitz_pdf(path: Path, images: list[str], author: str = None) -> Path:
    path = get_path(path)
    doc = fitz.open()

    for i, image_path in enumerate(images):
        img = fitz.open(image_path)
        rect = img[0].rect
        pdfbytes = img.convert_to_pdf()
        img.close()
        img_pdf = fitz.open("pdf", pdfbytes)
        page = doc.new_page(width=rect.width, height=rect.height)
        page.show_pdf_page(rect, img_pdf, 0)
        img_pdf.close()

    doc.set_metadata(
        {
            "title": unicode_to_latin1(path.stem),
            "author": author,
        }
    )

    doc.save(path)
    doc.close()

    return path


def canvas_pdf(path: Path, images: list[str], author: str = None) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=letter)

    pdf.setTitle(unicode_to_latin1(path.stem))
    pdf.setAuthor(author)

    for image in images:
        try:
            w, h = get_image_size(image)
            pdf.setPageSize((w, h))
            pdf.drawImage(image, x=0, y=0, width=w, height=h)
            pdf.showPage()
        except Exception as e:
            print(f"An error occurred while processing {image}: {str(e)}")
            continue

    pdf.save()
    return path


def images_to_pdf(path: Path, images: list[str], author: str = None) -> Path:
    path = get_path(path)
    try:
        with path.open("wb") as file:
            file.write(
                img2pdf.convert(
                    images,
                    author=author,
                    producer=author,
                    creator=author,
                    title=unicode_to_latin1(path.stem),
                )
            )
    except Exception:
        canvas_pdf(path, images, author=author)

    return path


def pil_img2pdf(path: Path, files: list[Path]) -> Path:
    img_list = [convert_img(img) for img in files]
    img_list[0].save(path, resolution=100.0, save_all=True, append_images=img_list[1:])
    for img in img_list:
        img.close()

    return path


def img2fpdf(path: Path, files: list[Path], author: str = None) -> Path:
    pdf = FPDF("P", "pt")
    for imageFile in files:
        img_bytes, width, height = pil_image(imageFile)

        pdf.add_page(format=(width, height))
        pdf.image(img_bytes, 0, 0, width, height)

        img_bytes.close()

    pdf.set_title(unicode_to_latin1(path.stem))
    pdf.set_author(author)
    pdf.output(str(path), "F")

    return path


def imgtopdf(path: Path, files: list[Path], author: str = "") -> Path:
    pdf_path = path.with_suffix(".pdf") if not path.suffix == ".pdf" else path
    try:
        img2fpdf(pdf_path, files, author=author)
    except Exception as e:
        print(f"Image to PDF failed with exception: {e}")
        pil_img2pdf(pdf_path, files)
    return pdf_path


def merge_pdfs(out: Path, pdfs: list[str], author: str = None, password: str = None) -> Path:
    out = get_path(out)
    result = fitz.open()

    for pdf in pdfs:
        with fitz.open(pdf) as file:
            result.insert_pdf(file)

    result.set_metadata(
        {
            "title": unicode_to_latin1(out.stem),
            "author": author,
        }
    )
    
    if password:
        result.save(out, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password)
    else:
        result.save(out)

    result.close()
    return out


def merge_cbzs(output_file: str | Path, cbz_files: list[str | Path], password: str = None):
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as merged_cbz:
        if password:
            merged_cbz.setpassword(password.encode())
        for cbz_file in cbz_files:
            with zipfile.ZipFile(cbz_file, 'r') as individual_cbz:
                for file_name in individual_cbz.namelist():
                    merged_cbz.writestr(file_name, individual_cbz.read(file_name))
    return output_file


def encrypt_pdf(file_path: Path | str, password):
    file_path = get_path(file_path)
    if not os.path.isdir("cache/encrypted/"):
        os.mkdir("cache/encrypted/")

    pdf = fitz.open(file_path)
    
    encryption = fitz.PDF_ENCRYPT_AES_256
    
    output_file = "cache/encrypted" / file_path.name
    pdf.save(output_file, encryption=encryption, user_pw=password)
    pdf.close()
    
    os.remove(file_path)
    return output_file
    