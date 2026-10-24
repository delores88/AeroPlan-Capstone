"""Small dependency-free PDF writer for a portable instructor summary.
Uses the PDF standard Helvetica fonts; no external assets, font downloads, or renderer.
"""
import textwrap

def ascii_text(s):
    return str(s).replace('–','-').replace('—','-').replace('·','/').replace('≥','>=').replace('α','alpha').replace('β','beta').replace('σ','sigma').replace('→','->').replace('²','2').replace('−','-').encode('cp1252','replace').decode('cp1252')

def esc(s):return ascii_text(s).replace('\\','\\\\').replace('(','\\(').replace(')','\\)')

class PDF:
    def __init__(self,label='RESEARCH EVIDENCE'):
        self.pages=[];self.label=label;self.new_page()
    def new_page(self):
        self.pages.append([]);self.y=726
        self.raw('0.08 0.14 0.23 rg 0 758 612 34 re f')
        self.at(44,770,'AEROPLAN LOCAL  /  '+self.label,9,True,color=(1,1,1))
    def raw(self,s):self.pages[-1].append(s)
    def at(self,x,y,text,size=10,bold=False,color=(.12,.18,.26)):
        self.raw(f'{color[0]} {color[1]} {color[2]} rg BT /{"F2" if bold else "F1"} {size} Tf 1 0 0 1 {x} {y} Tm ({esc(text)}) Tj ET')
    def need(self,h):
        if self.y-h<54:self.new_page()
    def heading(self,s,level=1):
        size=21 if level==1 else 13;self.need(size+30);self.at(44,self.y,s,size,True);self.y-=size+14
    def paragraph(self,s,size=10):
        text=ascii_text(s);width=int(520/(size*.54))
        for paragraph in text.split('\n'):
            for line in textwrap.wrap(paragraph,width=width,break_long_words=True,replace_whitespace=True) or ['']:
                self.need(size+5);self.at(44,self.y,line,size);self.y-=size+5
        self.y-=8
    def rule(self):self.need(10);self.raw(f'0.84 0.87 0.9 RG 44 {self.y} m 568 {self.y} l S');self.y-=14
    def table(self,headers,rows,widths):
        def header():
            self.need(26);self.raw(f'0.92 0.95 0.97 rg 44 {self.y-6} 524 23 re f');x=50
            for h,w in zip(headers,widths):self.at(x,self.y,h,8,True);x+=w
            self.y-=24
        header()
        for i,row in enumerate(rows):
            if self.y<75:self.new_page();header()
            x=50
            for value,w in zip(row,widths):
                s=ascii_text(value);limit=int(w/4.25)-1
                if len(s)>limit:s=s[:max(0,limit-2)]+'..'
                self.at(x,self.y,s,8);x+=w
            self.raw(f'0.91 0.93 0.95 RG 44 {self.y-6} m 568 {self.y-6} l S');self.y-=21
        self.y-=14
    def bytes(self):
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>']
        page_refs=[]
        for i,cmds in enumerate(self.pages):
            cmds=list(cmds)+[f'0.4 0.46 0.53 rg BT /F1 8 Tf 1 0 0 1 44 30 Tm (AeroPlan Local | {esc(self.label)} | Page {i+1} of {len(self.pages)}) Tj ET']
            stream='\n'.join(cmds).encode('cp1252');pnum=len(objects)+1;snum=pnum+1;page_refs.append(pnum)
            objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {snum} 0 R >>'.encode())
            objects.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
        objects[1]=f'<< /Type /Pages /Count {len(page_refs)} /Kids [{" ".join(f"{n} 0 R" for n in page_refs)}] >>'.encode()
        out=bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n');offsets=[0]
        for i,obj in enumerate(objects,1):offsets.append(len(out));out.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
        start=len(out);out.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
        for n in offsets[1:]:out.extend(f'{n:010d} 00000 n \n'.encode())
        out.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode());return bytes(out)
