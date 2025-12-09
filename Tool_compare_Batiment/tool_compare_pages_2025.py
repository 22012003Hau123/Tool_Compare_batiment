import sys

import fitz  # PyMuPDF


PAGE_SIZE_TOLERANCE = 0.02   # 2%
IMAGE_SIZE_TOLERANCE = 0.05  # 5%


def get_main_image_bbox(page: fitz.Page):
	"""
	Lấy bbox của hình ảnh có diện tích lớn nhất trên trang (xấp xỉ main image).
	Trả về fitz.Rect hoặc None nếu không có ảnh.
	"""
	img_list = page.get_images(full=True)
	if not img_list:
		return None

	text_dict = page.get_text("rawdict")
	best_rect = None
	best_area = 0

	for block in text_dict.get("blocks", []):
		if block["type"] == 1:  # image
			x0, y0, x1, y1 = block["bbox"]
			rect = fitz.Rect(x0, y0, x1, y1)
			area = rect.get_area()
			if area > best_area:
				best_area = area
				best_rect = rect

	return best_rect


def compare_pages(ref_page: fitz.Page, final_page: fitz.Page, page_index: int):
	"""
	So sánh 1 trang: kích thước page + hình chính.
	Nếu khác vượt ngưỡng => annotate lên final_page.
	"""
	annotations = []

	# --- So sánh kích thước trang ---
	ref_rect = ref_page.mediabox
	final_rect = final_page.mediabox

	ref_w, ref_h = ref_rect.width, ref_rect.height
	final_w, final_h = final_rect.width, final_rect.height

	dw = abs(final_w - ref_w) / ref_w if ref_w else 0
	dh = abs(final_h - ref_h) / ref_h if ref_h else 0

	if dw > PAGE_SIZE_TOLERANCE or dh > PAGE_SIZE_TOLERANCE:
		msg = (
			f"Page size diff (PAGES-2025 vs final): "
			f"W {ref_w:.1f}->{final_w:.1f} ({dw*100:.1f}%), "
			f"H {ref_h:.1f}->{final_h:.1f} ({dh*100:.1f}%)"
		)
		annotations.append(("page", final_rect, msg))

	# --- So sánh kích thước hình chính ---
	ref_img_rect = get_main_image_bbox(ref_page)
	final_img_rect = get_main_image_bbox(final_page)

	if ref_img_rect and final_img_rect:
		ref_w_i, ref_h_i = ref_img_rect.width, ref_img_rect.height
		final_w_i, final_h_i = final_img_rect.width, final_img_rect.height

		dw_i = abs(final_w_i - ref_w_i) / ref_w_i if ref_w_i else 0
		dh_i = abs(final_h_i - ref_h_i) / ref_h_i if ref_h_i else 0

		if dw_i > IMAGE_SIZE_TOLERANCE or dh_i > IMAGE_SIZE_TOLERANCE:
			msg = (
				f"Main image size diff: "
				f"W {ref_w_i:.1f}->{final_w_i:.1f} ({dw_i*100:.1f}%), "
				f"H {ref_h_i:.1f}->{final_h_i:.1f} ({dh_i*100:.1f}%)"
			)
			annotations.append(("image", final_img_rect, msg))

	# --- Tạo annotation trên PDF final ---
	for kind, rect, msg in annotations:
		try:
			annot = final_page.add_rect_annot(rect)
			annot.set_colors(stroke=(1, 0, 0))  # khung đỏ
			annot.set_border(width=1)
			annot.set_info(
				title="Mode1-PAGES-2025",
				content=msg,
				subject="Layout check" if kind == "page" else "Image check",
			)
			annot.update()
		except Exception as e:
			print(f"Error adding annotation on page {page_index}: {e}")


def main(ref_path: str, final_path: str, output_path: str | None = None):
	ref_doc = fitz.open(ref_path)
	final_doc = fitz.open(final_path)

	num_pages = min(ref_doc.page_count, final_doc.page_count)
	print(f"Comparing first {num_pages} pages...")

	for i in range(num_pages):
		ref_page = ref_doc.load_page(i)
		final_page = final_doc.load_page(i)
		compare_pages(ref_page, final_page, i)

	if output_path is None:
		base = final_path.rsplit(".", 1)[0]
		output_path = base + "_mode1_pages2025_diff.pdf"

	final_doc.save(output_path)
	ref_doc.close()
	final_doc.close()
	print(f"Saved annotated final PDF to: {output_path}")


if __name__ == "__main__":
	if len(sys.argv) < 3:
		print("Usage: python tool_compare_pages_2025.py <PAGES-2025.pdf> <FINAL.pdf> [output.pdf]")
		sys.exit(1)

	ref = sys.argv[1]
	final = sys.argv[2]
	out = sys.argv[3] if len(sys.argv) > 3 else None
	main(ref, final, out)
