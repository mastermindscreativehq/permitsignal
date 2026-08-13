from backend.app.services.document_downloader import (
    download_document,
)

from backend.app.parsers.pdf_parser import (
    parse_pdf,
)


AGENDA_URL = (
    "https://www.provo.gov/AgendaCenter/"
    "ViewFile/Agenda/_08122026-415"
)


print("=" * 70)
print("PERMITSIGNAL DOCUMENT PIPELINE")
print("=" * 70)

print()
print("[1/2] Downloading government agenda...")

pdf_path = download_document(
    AGENDA_URL
)

print(
    f"Downloaded: {pdf_path}"
)

print()
print("[2/2] Extracting PDF text...")

document = parse_pdf(
    pdf_path
)

print(
    f"Pages: {document.page_count}"
)

print(
    f"Characters extracted: "
    f"{len(document.text):,}"
)

print()
print("=" * 70)
print("FIRST 8,000 CHARACTERS")
print("=" * 70)

print(
    document.text[:8000]
)

print()
print("=" * 70)