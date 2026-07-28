from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.enum.text import WD_TAB_LEADER
from docx.enum.text import WD_LINE_SPACING
from docx.oxml import OxmlElement

def set_font(run, font_name, east_asia_font=None):
    run.font.name = font_name
    if east_asia_font:
        rPr = run.font.element.rPr
        if rPr is None:
            rPr = run.font.element.makeelement('rPr')
            run.font.element.append(rPr)
        # Set East Asia font
        rFonts = rPr.find(qn('w:rFonts'))
        if rFonts is None:
            rFonts = rPr.makeelement(qn('w:rFonts'))
            rPr.append(rFonts)
        rFonts.set(qn('w:eastAsia'), east_asia_font)

def force_font(style, font_name, size_pt=None, color=None, bold=False):
    """
    Forcefully set font for a style, removing theme references and setting all font slots.
    """
    if size_pt:
        style.font.size = Pt(size_pt)
    if color:
        style.font.color.rgb = RGBColor(*color)
    style.font.bold = bold
    style.font.name = font_name
    
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    
    # Remove theme attributes if they exist to prevent overriding
    for k in [
        qn('w:asciiTheme'),
        qn('w:eastAsiaTheme'),
        qn('w:hAnsiTheme'),
        qn('w:csTheme'),
        qn('w:cstheme'),
    ]:
        if k in rFonts.attrib:
            del rFonts.attrib[k]
        
    # Set explicit font names
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:eastAsia'), font_name)
    rFonts.set(qn('w:hAnsi'), font_name)
    rFonts.set(qn('w:cs'), font_name)
    
    # Set hint to eastAsia to prioritize CJK font choice
    rFonts.set(qn('w:hint'), 'eastAsia')

def create_template(name, base_font="Microsoft YaHei", east_asia_font="Microsoft YaHei", title_color=(0, 0, 0)):
    doc = Document()
    
    # Configure Normal Style
    force_font(doc.styles['Normal'], base_font, 12)
    # Line spacing for Normal
    normal_pf = doc.styles['Normal'].paragraph_format
    normal_pf.line_spacing = 1.3
    # Remove any paragraph borders in styles (avoid accidental horizontal lines)
    try:
        ppr = doc.styles['Normal']._element.get_or_add_pPr()
        for border_tag in ['top', 'bottom', 'left', 'right', 'between', 'bar']:
            b = ppr.find(qn(f'w:pBdr'))
            if b is not None:
                ppr.remove(b)
    except Exception:
        pass
    
    # Configure Title
    force_font(doc.styles['Title'], base_font, 24, title_color, True)
    
    # Configure Headings 1-6
    # It's good practice to configure more levels just in case
    for i in range(1, 7):
        try:
            style_name = f'Heading {i}'
            # Check if style exists, if not, access it (docx creates it if standard)
            # Adjust size roughly
            size = 18 - (i * 1) 
            if size < 12: size = 12
            
            force_font(doc.styles[style_name], base_font, size, title_color, True)
            pf = doc.styles[style_name].paragraph_format
            pf.space_before = Pt(12)
            pf.space_after = Pt(6)
            if i == 1:
                pf.page_break_before = True
        except KeyError:
            pass # Should not happen for standard styles

    # Try to enforce TOC styles with dotted leaders and YaHei
    for toc_style in ['TOC 1', 'TOC 2', 'TOC 3']:
        try:
            s = doc.styles[toc_style]
            force_font(s, base_font, 12)
            pf = s.paragraph_format
            # Add a right-aligned tab stop with dotted leader near right margin (~16cm)
            try:
                pf.tab_stops.add_tab_stop(Cm(16), WD_TAB_LEADER.DOTS)
            except Exception:
                pass
        except KeyError:
            continue

    # Code styles: Consolas, smaller size, light gray background via highlight
    for code_style in ['Code', 'Code Block', 'CodeBlock', 'Source Code', 'Verbatim Char', 'Verbatim Block']:
        try:
            s = doc.styles[code_style]
            force_font(s, 'Consolas', 10)
            try:
                s.font.highlight_color = 3  # WD_COLOR_INDEX.GRAY_25 (avoid import dependency on older versions)
            except Exception:
                pass
        except KeyError:
            continue

    doc.save(f'templates/{name}.docx')

if __name__ == "__main__":
    # All templates updated to use Microsoft YaHei (微软雅黑) as requested
    
    # Official (Formatted like official doc but with YaHei)
    create_template("official", "Microsoft YaHei", "Microsoft YaHei", (0, 0, 0))
    
    # Internet (Modern, Blue)
    create_template("internet", "Microsoft YaHei", "Microsoft YaHei", (0, 102, 204))
    
    # Academic (Serif-like structure but with YaHei font)
    create_template("academic", "Microsoft YaHei", "Microsoft YaHei", (0, 0, 0))
    print("Templates created (All Microsoft YaHei).")
