import sys
from collections import Counter

import fitz  # PyMuPDF

CASE_INSENSITIVE = True
IGNORE_QUOTES = True


def _normalize_word(word: str) -> str:
	if CASE_INSENSITIVE:
		word = word.lower()
	if IGNORE_QUOTES:
		word = (
			word.replace("'", "'")
			.replace("'", "'")
			.replace("ʼ", "'")
			.replace(""", '"')
			.replace(""", '"')
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
			words.append({
				"text": text, 
				"rect": fitz.Rect(x0, y0, x1, y1),
				"highlight_color": None  # Will be set by comparison
			})
		pages.append({"page": page_index, "words": words})
	doc.close()
	return pages


def align_words_assemblage(ref_words_data, final_words_data):
	"""
	Exact copy of PDF-Diff-Viewer align logic.
	Sets highlight_color on word dicts.
	"""
	from difflib import SequenceMatcher
	
	# Normalize for comparison
	ref_norm = [_normalize_word(w["text"]) for w in ref_words_data]
	final_norm = [_normalize_word(w["text"]) for w in final_words_data]
	
	# Global move detection - count ALL occurrences
	ref_counter = Counter(ref_norm)
	final_counter = Counter(final_norm)
	
	s = SequenceMatcher(None, ref_norm, final_norm)
	
	idx1_current = 0
	idx2_current = 0
	
	for tag, i1, i2, j1, j2 in s.get_opcodes():
		# Debug: print operations
		if tag != 'equal':
			ref_words_in_op = [ref_norm[i] for i in range(i1, min(i2, len(ref_norm)))]
			final_words_in_op = [final_norm[j] for j in range(j1, min(j2, len(final_norm)))]
			print(f"  {tag}: ref[{i1}:{i2}]={ref_words_in_op[:5]} | final[{j1}:{j2}]={final_words_in_op[:5]}")
		
		if tag == 'equal':
			# No highlighting
			for k in range(i2 - i1):
				ref_words_data[idx1_current + k]["highlight_color"] = None
				final_words_data[idx2_current + k]["highlight_color"] = None
			idx1_current += (i2 - i1)
			idx2_current += (j2 - j1)
			
		elif tag == 'delete':
			# Check EACH word if moved
			for k in range(i2 - i1):
				word_norm = ref_norm[i1 + k]
				is_moved = word_norm in final_counter and final_counter[word_norm] > 0
				ref_words_data[idx1_current + k]["highlight_color"] = "blue" if is_moved else "red"
			idx1_current += (i2 - i1)
			
		elif tag == 'insert':
			# Check EACH word if moved
			for k in range(j2 - j1):
				word_norm = final_norm[j1 + k]
				is_moved = word_norm in ref_counter and ref_counter[word_norm] > 0
				final_words_data[idx2_current + k]["highlight_color"] = "blue" if is_moved else "green"
			idx2_current += (j2 - j1)
			
		elif tag == 'replace':
			# For replace, check EACH word individually if it's moved
			# A word in replace might still exist elsewhere (moved)
			for k in range(i2 - i1):
				word_norm = ref_norm[i1 + k]
				# Check if this word exists in final doc (anywhere)
				is_moved = word_norm in final_counter and final_counter[word_norm] > 0
				ref_words_data[idx1_current + k]["highlight_color"] = "blue" if is_moved else "red"
			
			for k in range(j2 - j1):
				word_norm = final_norm[j1 + k]
				# Check if this word existed in ref doc (anywhere)
				is_moved = word_norm in ref_counter and ref_counter[word_norm] > 0
				final_words_data[idx2_current + k]["highlight_color"] = "blue" if is_moved else "green"
			
			idx1_current += (i2 - i1)
			idx2_current += (j2 - j1)
	
	return ref_words_data, final_words_data


def apply_highlights_to_page(page: fitz.Page, words_data, page_num: int):
	"""
	Apply highlights to a PDF page based on word highlight_color.
	Exact copy of PDF-Diff-Viewer apply_annotations_to_pdf_pages logic.
	"""
	# Color mapping (RGB float)
	color_map = {
		"red": (1, 0, 0),
		"green": (0, 1, 0),
		"blue": (0, 0, 1)
	}
	
	highlights_added = 0
	
	for word in words_data:
		if not word["highlight_color"]:
			continue
		
		color = color_map.get(word["highlight_color"])
		if not color:
			continue
		
		try:
			annot = page.add_highlight_annot(word["rect"])
			annot.set_colors(stroke=color)
			annot.set_opacity(0.3)
			annot.set_info(title="Mode3-Comparison")
			annot.update()
			highlights_added += 1
		except Exception as e:
			print(f"Error adding highlight on page {page_num}: {e}")
	
	return highlights_added


def compare_pages_assemblage(ref_page: fitz.Page, ref_page_dict, final_page: fitz.Page, page_index: int):
	"""
	Mode 3 comparison using exact PDF-Diff-Viewer logic.
	
	Process:
	1. align_words_assemblage() - sets highlight_color on words
	2. apply_highlights_to_page() - applies highlights to PDFs
	"""
	ref_words_data = ref_page_dict["words"]
	
	# Extract final words
	final_words_raw = final_page.get_text("words")
	final_words_data = [
		{
			"text": t,
			"rect": fitz.Rect(x0, y0, x1, y1),
			"highlight_color": None
		}
		for x0, y0, x1, y1, t, *_ in final_words_raw
	]
	
	# Align and set colors (modifies in-place)
	align_words_assemblage(ref_words_data, final_words_data)
	
	# Apply highlights to both pages
	ref_count = apply_highlights_to_page(ref_page, ref_words_data, page_index)
	final_count = apply_highlights_to_page(final_page, final_words_data, page_index)
	
	print(f"Page {page_index}: {ref_count} ref, {final_count} final highlights")


def main(ref_path: str, final_path: str, output_ref: str | None = None, output_final: str | None = None):
	"""Compare and annotate BOTH PDFs."""
	# Open BOTH PDFs
	ref_doc = fitz.open(ref_path)
	ref_pages_data = extract_page_words_with_boxes(ref_path)
	final_doc = fitz.open(final_path)

	num_pages = min(len(ref_pages_data), final_doc.page_count, ref_doc.page_count)
	print(f"Mode 3 (Assemblage): comparing {num_pages} pages...")

	for i in range(num_pages):
		ref_page = ref_doc.load_page(i)
		ref_page_dict = ref_pages_data[i]
		final_page = final_doc.load_page(i)
		compare_pages_assemblage(ref_page, ref_page_dict, final_page, i)

	# Determine output paths
	if output_ref is None:
		output_ref = ref_path.rsplit(".", 1)[0] + "_mode3_ref.pdf"
	if output_final is None:
		output_final = final_path.rsplit(".", 1)[0] + "_mode3_final.pdf"
	
	# Save BOTH annotated PDFs
	ref_doc.save(output_ref, garbage=4, deflate=True)
	ref_doc.close()
	print(f"Saved reference: {output_ref}")
	
	final_doc.save(output_final, garbage=4, deflate=True)
	final_doc.close()
	print(f"Saved final: {output_final}")
	
	return output_ref, output_final


if __name__ == "__main__":
	if len(sys.argv) < 3:
		print("Usage: python tool_compare_assemblage.py <ref.pdf> <final.pdf> [output_ref.pdf] [output_final.pdf]")
		sys.exit(1)

	ref = sys.argv[1]
	final = sys.argv[2]
	out_ref = sys.argv[3] if len(sys.argv) > 3 else None
	out_final = sys.argv[4] if len(sys.argv) > 4 else None
	main(ref, final, out_ref, out_final)
