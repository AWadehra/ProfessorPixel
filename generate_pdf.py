"""Generate a professional-looking contract PDF."""
from fpdf import FPDF

class ContractPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(130, 130, 130)
            self.cell(0, 5, "NovaBright Technologies, Inc. -- Freelance Services Agreement", align="L")
            self.cell(0, 5, f"Page {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, "CONFIDENTIAL -- For authorized use only", align="C")


pdf = ContractPDF()
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_page()

# Read contract text and sanitize unicode
with open("sample-contract.md", "r") as f:
    raw = f.read()

# Replace problematic unicode chars with latin-1 equivalents
raw = raw.replace("\u2014", "--")  # em dash
raw = raw.replace("\u2013", "-")   # en dash
raw = raw.replace("\u2018", "'")   # left single quote
raw = raw.replace("\u2019", "'")   # right single quote
raw = raw.replace("\u201c", '"')   # left double quote
raw = raw.replace("\u201d", '"')   # right double quote
raw = raw.replace("\u2026", "...")  # ellipsis
raw = raw.replace("\u00a7", "S.")  # section sign

lines = raw.split("\n")

# Title
pdf.set_font("Helvetica", "B", 16)
pdf.set_text_color(20, 20, 40)
pdf.cell(0, 12, "FREELANCE SERVICES AGREEMENT", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(2)

# Decorative line
pdf.set_draw_color(60, 60, 120)
pdf.set_line_width(0.8)
pdf.line(pdf.l_margin + 30, pdf.get_y(), pdf.w - pdf.r_margin - 30, pdf.get_y())
pdf.ln(8)

# Process lines
skip_first = True  # skip the "FREELANCE SERVICES AGREEMENT" line
section_headers = {
    "1. SCOPE OF WORK", "2. TERM AND TERMINATION", "3. COMPENSATION AND PAYMENT",
    "4. INTELLECTUAL PROPERTY", "5. CONFIDENTIALITY", "6. REPRESENTATIONS AND WARRANTIES",
    "7. INDEMNIFICATION", "8. LIMITATION OF LIABILITY", "9. NON-COMPETITION AND NON-SOLICITATION",
    "10. INDEPENDENT CONTRACTOR STATUS", "11. DISPUTE RESOLUTION", "12. GENERAL PROVISIONS",
    "IN WITNESS WHEREOF", "EXHIBIT A", "COMPANY:", "CONTRACTOR:",
}

for line in lines:
    stripped = line.strip()
    if not stripped:
        pdf.ln(3)
        continue

    if skip_first and stripped == "FREELANCE SERVICES AGREEMENT":
        skip_first = False
        continue

    # Check if it's a major section header
    is_header = any(stripped.startswith(h) for h in section_headers)
    is_exhibit = stripped.startswith("EXHIBIT A")
    is_witness = stripped.startswith("IN WITNESS WHEREOF")
    is_sub = any(stripped.startswith(f"{i}.{j}") for i in range(1, 13) for j in range(1, 10))
    is_caps = stripped.isupper() and len(stripped) > 20

    if is_exhibit:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(20, 20, 40)
        pdf.cell(0, 10, stripped, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(60, 60, 120)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(4)
    elif is_witness:
        pdf.ln(8)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(20, 20, 40)
        pdf.multi_cell(0, 5.5, stripped)
        pdf.ln(4)
    elif is_header and not is_exhibit:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(20, 20, 60)
        pdf.cell(0, 7, stripped, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    elif is_sub:
        pdf.ln(1)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(40, 40, 60)
        # Split on first period-space after subsection number
        parts = stripped.split(". ", 1)
        if len(parts) == 2:
            label = parts[0] + "."
            rest = parts[1]
            # Check if rest starts with a defined term
            pdf.set_x(pdf.l_margin + 2)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(40, 40, 60)
            w = pdf.get_string_width(label + " ")
            pdf.cell(w, 5, label + " ")
            # Title portion (before the first period in rest)
            title_end = rest.find(".")
            if title_end > 0 and title_end < 40:
                title = rest[:title_end + 1]
                body = rest[title_end + 1:].strip()
                pdf.set_font("Helvetica", "B", 9)
                tw = pdf.get_string_width(title + " ")
                pdf.cell(tw, 5, title + " ")
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(30, 30, 30)
                pdf.multi_cell(0, 5, body)
            else:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(30, 30, 30)
                pdf.multi_cell(0, 5, rest)
        else:
            pdf.multi_cell(0, 5, stripped)
    elif is_caps:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(30, 30, 30)
        pdf.multi_cell(0, 4.5, stripped)
    elif stripped.startswith("By: ___") or stripped.startswith("Name: ___") or stripped.startswith("Email: ___"):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 30, 30)
        pdf.ln(8)
        pdf.cell(0, 5, stripped, new_x="LMARGIN", new_y="NEXT")
    elif stripped.startswith("By:") or stripped.startswith("Name:") or stripped.startswith("Title:") or stripped.startswith("Email:"):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 5, stripped, new_x="LMARGIN", new_y="NEXT")
    elif stripped.startswith("- ") or stripped.startswith("   -"):
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(30, 30, 30)
        indent = 8 if stripped.startswith("   -") else 5
        pdf.set_x(pdf.l_margin + indent)
        text = stripped.lstrip(" -").strip()
        pdf.multi_cell(0, 4.5, f"-  {text}")
        pdf.ln(0.5)
    elif stripped.startswith("Project:") or stripped.startswith("Total Fixed") or stripped.startswith("Payment ") or stripped.startswith("Company Point"):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 30, 30)
        pdf.set_x(pdf.l_margin + 3)
        pdf.multi_cell(0, 5, stripped)
    elif stripped.startswith("Milestone"):
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(30, 30, 30)
        pdf.set_x(pdf.l_margin + 6)
        pdf.multi_cell(0, 4.5, f"-  {stripped.lstrip('- ').strip()}")
        pdf.ln(0.5)
    else:
        # Regular paragraph
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 30, 30)
        pdf.multi_cell(0, 5, stripped)

# Signature lines
pdf.ln(6)

# Output
output_path = "NovaBright_Freelance_Services_Agreement.pdf"
pdf.output(output_path)
print(f"PDF generated: {output_path}")
print(f"Pages: {pdf.pages_count}")
