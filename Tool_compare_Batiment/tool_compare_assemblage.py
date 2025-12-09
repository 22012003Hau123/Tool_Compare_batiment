import sys

import fitz  # PyMuPDF

CASE_INSENSITIVE = True
IGNORE_QUOTES = True


def _normalize_word(word: str) -> str:
	if CASE_INSENSITIVE:
		word = word.lower()
	if IGNORE_QUOTES:
		word = (
			word.replace("‘", "'")
			.replace("’", "'")
			.replace("ʼ", "'")
			.replace("“", '"')
			.replace("”", '"')
		)
	return word


def extract_page_words_with_boxes(pdf_path: str):
	doc = fitz.open(pdf_path)
	pages = []
	for page_index in range(doc.page_count):
		page = doc.load_page(page_index)
		words_raw = page.get_text("words")
		words = []
		for x0, y0, x1, y1, text, *_ in words_raw:
			words.append({"text": text, "rect": fitz.Rect(x0, y0, x1, y1)})
		pages.append({"page": page_index, "words": words})
	doc.close()
	return pages


def compare_pages_assemblage(ref_page_dict, final_page: fitz.Page, page_index: int):
	"""
	Mode 3 – 0ASSEMBLAGE_PDF:
	So sánh texte (word-level) giữa export InDesign brut và PDF final,
	annotate trực tiếp lên final; tập trung bắt lỗi thao tác graphiste.
	"""
	from difflib import SequenceMatcher

	ref_words_info = ref_page_dict["words"]
	ref_words = [w["text"] for w in ref_words_info]
	final_words_raw = final_page.get_text("words")
	final_words_info = [
		{"text": t, "rect": fitz.Rect(x0, y0, x1, y1)}
		for x0, y0, x1, y1, t, *_ in final_words_raw
	]
	final_words = [w["text"] for w in final_words_info]

	ref_norm = [_normalize_word(w) for w in ref_words]
	final_norm = [_normalize_word(w) for w in final_words]

	s = SequenceMatcher(None, ref_norm, final_norm)

	for tag, i1, i2, j1, j2 in s.get_opcodes():
		if tag == "equal":
			continue
		if tag in ("delete", "replace"):
			# texte bị mất so với 0ASSEMBLAGE
			for k in range(i1, i2):
				rect = ref_words_info[k]["rect"]
				try:
					annot = final_page.add_rect_annot(rect)
					annot.set_colors(stroke=(1, 0.5, 0))  # cam
					annot.set_border(width=0.5)
					annot.set_info(
						title="Mode3-ASSEMBLAGE",
						content=f"Missing vs Assemblage: '{ref_words_info[k]['text']}'",
						subject="Missing text",
					)
					annot.update()
				except Exception as e:
					print(f"Mode3: error adding delete annot on page {page_index}: {e}")
		if tag in ("insert", "replace"):
			# texte thêm vào so với 0ASSEMBLAGE (có thể là lỗi copy nhầm, (w) còn sót, v.v.)
			for k in range(j1, j2):
				rect = final_words_info[k]["rect"]
				try:
					annot = final_page.add_rect_annot(rect)
					annot.set_colors(stroke=(0, 0, 1))  # xanh dương
					annot.set_border(width=0.5)
					annot.set_info(
						title="Mode3-ASSEMBLAGE",
						content=f"Extra vs Assemblage: '{final_words_info[k]['text']}'",
						subject="Extra text",
					)
					annot.update()
				except Exception as e:
					print(f"Mode3: error adding insert annot on page {page_index}: {e}")


def main(ref_path: str, final_path: str, output_path: str | None = None):
	ref_pages = extract_page_words_with_boxes(ref_path)
	final_doc = fitz.open(final_path)

	num_pages = min(len(ref_pages), final_doc.page_count)
	print(f"Mode 3 (Assemblage): comparing first {num_pages} pages...")

	for i in range(num_pages):
		ref_page_dict = ref_pages[i]
		final_page = final_doc.load_page(i)
		compare_pages_assemblage(ref_page_dict, final_page, i)

	if output_path is None:
		base = final_path.rsplit(".", 1)[0]
		output_path = base + "_mode3_assemblage_diff.pdf"

	final_doc.save(output_path)
	final_doc.close()
	print(f"Saved annotated final PDF to: {output_path}")


if __name__ == "__main__":
	if len(sys.argv) < 3:
		print("Usage: python tool_compare_assemblage.py <0ASSEMBLAGE_PDF.pdf> <FINAL.pdf> [output.pdf]")
		sys.exit(1)

	ref = sys.argv[1]
	final = sys.argv[2]
	out = sys.argv[3] if len(sys.argv) > 3 else None
	main(ref, final, out)
