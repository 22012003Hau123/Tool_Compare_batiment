import sys
import fitz
import os
from PIL import Image
import imagehash

# ============================================================
# EXTRACT PRODUCT IMAGES FROM PDF BLOCKS (100% WORKS)
# ============================================================

def extract_products(pdf_path, out_dir):
	os.makedirs(out_dir, exist_ok=True)
	doc = fitz.open(pdf_path)

	products = []
	idx = 0

	for page_index, page in enumerate(doc):
		raw = page.get_text("rawdict")

		for block in raw["blocks"]:
			if block["type"] in [1, 2]:  # image block OR form XObject block
				bbox = block["bbox"]
				x0, y0, x1, y1 = bbox

				width_pt = x1 - x0
				height_pt = y1 - y0

				width_px = width_pt * 96 / 72
				height_px = height_pt * 96 / 72

				r = fitz.Rect(bbox)
				pix = page.get_pixmap(matrix=fitz.Matrix(2,2), clip=r)

				filename = f"{out_dir}/product_{idx}.png"
				pix.save(filename)

				products.append({
					"file": filename,
					"page": page_index,
					"width_pt": width_pt,
					"height_pt": height_pt,
					"width_px": width_px,
					"height_px": height_px,
					"bbox": bbox
				})
				idx += 1

	doc.close()
	return products


# ============================================================
# IMAGE HASH FOR PAIRING
# ============================================================

def compute_hash(path):
	img = Image.open(path).convert("RGB")
	return imagehash.phash(img)

def pair_products(list1, list2):
	for p in list1:
		p["hash"] = compute_hash(p["file"])
	for p in list2:
		p["hash"] = compute_hash(p["file"])

	pairs = []
	for p1 in list1:
		best = None
		best_dist = 9999
		for p2 in list2:
			dist = abs(p1["hash"] - p2["hash"])
			if dist < best_dist:
				best_dist = dist
				best = p2
		pairs.append((p1, best, best_dist))
	return pairs


# ============================================================
# COMPARE SIZES (WITH ANNOTATION - ENHANCED)
# ============================================================

def compare_pairs(pairs, pdf2_path=None, output_path=None):
	"""
	Compare product sizes and optionally annotate PDF.
	
	Args:
		pairs: List of (p1, p2, distance) tuples
		pdf2_path: Path to PDF2 for annotation (optional)
		output_path: Path to save annotated PDF (optional)
	"""
	print("\n============== PRODUCT SIZE COMPARISON (hash < 24) ==============\n")

	# Open PDF2 for annotation if paths provided
	doc = None
	if pdf2_path and output_path:
		doc = fitz.open(pdf2_path)
	
	annotations_added = 0

	for p1, p2, dist in pairs:
		if dist > 24:
			# BỎ QUA nếu không đủ giống nhau
			continue

		w1, h1 = p1["width_px"], p1["height_px"]
		w2, h2 = p2["width_px"], p2["height_px"]

		scale_w = (w2 / w1) * 100
		scale_h = (h2 / h1) * 100

		print(f"{os.path.basename(p1['file'])}  <-->  {os.path.basename(p2['file'])}")
		print(f"  Hash distance : {dist}")
		print(f"  PDF1 size     : {w1:.1f} × {h1:.1f}px")
		print(f"  PDF2 size     : {w2:.1f} × {h2:.1f}px")
		print(f"  Scale         : W={scale_w:.2f}%, H={scale_h:.2f}%\n")
		
		# ANNOTATION: Add to PDF if doc is open
		if doc:
			page = doc.load_page(p2["page"])
			bbox = p2["bbox"]
			rect = fitz.Rect(bbox)
			
			# Add rectangle annotation
			annot = page.add_rect_annot(rect)
			annot.set_colors(stroke=(0, 0, 1))  # Blue
			annot.set_border(width=1.5)
			annot.set_opacity(0.4)
			
			# Add text info
			annotation_text = (
				f"PDF1 size: {w1:.1f} × {h1:.1f}px\n"
				f"PDF2 size: {w2:.1f} × {h2:.1f}px\n"
				f"Scale: W={scale_w:.1f}%, H={scale_h:.1f}%"
			)
			annot.set_info(
				title="Product-Size-Compare",
				content=annotation_text
			)
			annot.update()
			annotations_added += 1
	
	# Save annotated PDF
	if doc:
		doc.save(output_path, garbage=4, deflate=True)
		doc.close()
		print(f"\n✓ Added {annotations_added} annotations to {output_path}\n")



# ============================================================
# MAIN
# ============================================================

def run(pdf1, pdf2, output_pdf=None):
	"""
	Main function to run product comparison.
	
	Args:
		pdf1: Path to reference PDF
		pdf2: Path to final PDF
		output_pdf: Path to save annotated PDF (optional)
	"""
	print("[1] Extracting product blocks...")
	list1 = extract_products(pdf1, "pdf1_products")
	list2 = extract_products(pdf2, "pdf2_products")

	print(f"Found {len(list1)} products in PDF1")
	print(f"Found {len(list2)} products in PDF2")

	print("[2] Pairing products...")
	pairs = pair_products(list1, list2)

	print("[3] Compare sizes...")
	if output_pdf:
		compare_pairs(pairs, pdf2, output_pdf)
	else:
		compare_pairs(pairs)


# ============================================================
# BACKWARD COMPATIBILITY
# ============================================================

PAGE_SIZE_TOLERANCE = 0.02
IMAGE_SIZE_TOLERANCE = 0.05

def get_main_image_bbox(page: fitz.Page):
	"""Legacy function for backward compatibility."""
	text_dict = page.get_text("rawdict")
	best_rect = None
	best_area = 0
	
	for block in text_dict.get("blocks", []):
		if block["type"] == 1:
			x0, y0, x1, y1 = block["bbox"]
			rect = fitz.Rect(x0, y0, x1, y1)
			area = rect.get_area()
			if area > best_area:
				best_area = area
				best_rect = rect
	
	return best_rect

def compare_pages(ref_page: fitz.Page, final_page: fitz.Page, page_index: int):
	"""Legacy stub for streamlit compatibility."""
	print(f"Warning: compare_pages() is deprecated")
	return []

def compare_pages_2025(ref_path: str, final_path: str, output_path: str = None):
	"""Wrapper for streamlit integration."""
	if output_path is None:
		output_path = final_path.rsplit(".", 1)[0] + "_mode1.pdf"
	
	run(ref_path, final_path, output_path)
	
	results = {
		"output_pdf": output_path
	}
	return output_path, results


# RUN from command line
if __name__ == "__main__":
	if len(sys.argv) >= 3:
		pdf1 = sys.argv[1]
		pdf2 = sys.argv[2]
		output = sys.argv[3] if len(sys.argv) > 3 else None
		run(pdf1, pdf2, output)
	else:
		print("Usage: python tool_compare_pages_2025.py <pdf1> <pdf2> [output.pdf]")
