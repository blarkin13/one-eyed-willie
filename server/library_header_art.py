"""Transparent default library masthead artwork, generated locally as PNG.

No external resources, fonts, or network calls are required. The decoration
is intentionally subdued so it can sit behind legible library headings.
"""
from functools import lru_cache
from io import BytesIO
from math import cos, sin, pi

from PIL import Image, ImageDraw

BASE = (190, 216, 237)


def _polyline(draw, points, alpha=135, width=3):
    draw.line(points, fill=(*BASE, alpha), width=width, joint="curve")


def _movie(draw):
    # Filmstrip unfurls toward the left from a distressed classic reel.
    for baseline, phase in [(235, 0), (287, 1.6)]:
        ribbon = []
        for x in range(12, 858, 5):
            y = baseline + 33 * sin((x / 110) + phase) - (x / 900) * 10
            ribbon.append((x, y))
        _polyline(draw, ribbon, 104, 19)
        _polyline(draw, [(x, y-8) for x, y in ribbon], 196, 3)
        _polyline(draw, [(x, y+8) for x, y in ribbon], 196, 3)
        for i in range(10, len(ribbon)-10, 6):
            x,y=ribbon[i]
            draw.line((x,y-9,x,y+9),fill=(*BASE,110),width=3)
    cx,cy=672,170
    for r, alpha, width in [(130,75,6),(120,179,6),(106,95,2),(37,170,5)]:
        draw.ellipse((cx-r,cy-r,cx+r,cy+r),outline=(*BASE,alpha),width=width)
    for angle in range(5):
        a=angle*2*pi/5-pi/2
        px,py=cx+76*cos(a),cy+76*sin(a)
        draw.ellipse((px-34,py-34,px+34,py+34),outline=(*BASE,190),width=8)
        draw.ellipse((px-27,py-27,px+27,py+27),fill=(0,0,0,0))
    for radius in (15,25):
        draw.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),outline=(*BASE,205),width=3)
    for j in range(11):
        a=j*2*pi/11
        x,y=cx+110*cos(a),cy+110*sin(a)
        draw.ellipse((x-2,y-2,x+2,y+2),fill=(*BASE,175))


def _television(draw):
    # Vintage CRT television, aerial and soft signal rings.
    draw.rounded_rectangle((475,95,807,308),radius=48,outline=(*BASE,188),width=8)
    draw.rounded_rectangle((494,114,722,286),radius=30,outline=(*BASE,155),width=6)
    draw.rounded_rectangle((516,133,699,271),radius=36,fill=(*BASE,24),outline=(*BASE,102),width=3)
    draw.line((635,95,569,33),fill=(*BASE,152),width=6)
    draw.line((635,95,712,26),fill=(*BASE,152),width=6)
    draw.ellipse((563,27,577,41),fill=(*BASE,175))
    draw.ellipse((705,19,719,33),fill=(*BASE,175))
    for y in range(150,263,16):
        draw.line((529,y,683,y),fill=(*BASE,55),width=3)
    for y in (185,230):
        draw.ellipse((752,y-14,779,y+13),outline=(*BASE,185),width=5)
    for x in (554,738):
        draw.line((x,309,x-12,331),fill=(*BASE,169),width=6)
    for index in range(4):
        x=360-index*66
        draw.arc((x-85,120-index*18,x+130,360-index*8),-77,75,
                 fill=(*BASE,max(33,100-index*19)),width=4)
    for x in range(30,450,30):
        y=210+17*sin(x/32)
        draw.line((x,y,x+11,y),fill=(*BASE,60),width=3)


@lru_cache(maxsize=2)
def default_png(kind: str) -> bytes:
    if kind not in ("movies", "tv"):
        raise ValueError("Unsupported library type")
    multiplier = 2
    image = Image.new("RGBA", (900*multiplier,360*multiplier),(0,0,0,0))
    # Draw at full resolution for crisp edges on high-density screens.
    draw = ImageDraw.Draw(image)
    class Scaled:
        def line(self,coords,**kw):
            kw["width"]=kw.get("width",1)*multiplier
            if coords and isinstance(coords[0], (tuple, list)):
                points=[(x*multiplier,y*multiplier) for x,y in coords]
            else:
                points=tuple(v*multiplier for v in coords)
            draw.line(points,**kw)
        def ellipse(self,rect,**kw):
            if "width" in kw:kw["width"]*=multiplier
            draw.ellipse(tuple(v*multiplier for v in rect),**kw)
        def arc(self,rect,*args,**kw):
            if "width" in kw:kw["width"]*=multiplier
            draw.arc(tuple(v*multiplier for v in rect),*args,**kw)
        def rounded_rectangle(self,rect,**kw):
            kw["radius"]*=multiplier
            if "width" in kw:kw["width"]*=multiplier
            draw.rounded_rectangle(tuple(v*multiplier for v in rect),**kw)
    pencil=Scaled()
    if kind=="movies":
        _movie(pencil)
    else:
        _television(pencil)
    image=image.resize((900,360),Image.Resampling.LANCZOS)
    output=BytesIO()
    image.save(output,format="PNG",optimize=True)
    return output.getvalue()
