"""Five independent, three-scene local videos. No publishing or DB access."""
import json, subprocess, html, zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps, ImageChops
from template import ROOT, OUT, DATA, font, textblock, RED, INK, BG, money, rounded_asset, wrap

COPY=[
    'Crispy dog + cartofi, la Difereat Nicolina.',
    'Soluție pentru pardoseli și alte suprafețe. Recipient de 1 litru.',
    'Acrisyl KP 1.2, găleată de 25 kg. Preț pentru varianta albă; poate varia în funcție de culoare.',
    'Vas WC suspendat, Rimless, din porțelan. Dimensiuni: 370 × 560 × 440 mm.',
    'Centrală în condensare Viessmann Vitodens 100-W, 25 kW, cu kit inclus. Garanție: 2 ani.',
]

def base(header=True):
    im=Image.new('RGB',(1080,1920),BG)
    d=ImageDraw.Draw(im)
    brand=Image.open(ROOT/'assets/pinfers-logo.png').convert('RGBA')
    brand=brand.crop(brand.getchannel('A').getbbox())
    if header:
        small=ImageOps.contain(brand,(78,68))
        im.paste(small,(36,16),small)
    return im,d,brand

def explanation(index,item):
    im,d,_=base(); o,l=item['offer'],item['location']
    logo=Image.open(ROOT/'assets'/f'{index}-logo.img').convert('RGBA')
    white=Image.new('RGBA',logo.size,'white')
    white.alpha_composite(logo)
    bounds=ImageChops.difference(white.convert('RGB'),Image.new('RGB',logo.size,'white')).convert('L').point(lambda p: 255 if p>20 else 0).getbbox()
    if bounds: logo=logo.crop(bounds)
    logo=ImageOps.contain(logo,(400,260))
    logo=rounded_asset(logo,32)
    d.rounded_rectangle((300,110,780,400),radius=35,fill='white')
    im.paste(logo,((1080-logo.width)//2,125+(260-logo.height)//2),logo)
    def centered(text,y,size,width=930,bold=False,color=INK,max_lines=5):
        lines=wrap(d,text,size,width,bold)
        while len(lines)>max_lines and size>24:
            size-=2; lines=wrap(d,text,size,width,bold)
        if len(lines)>max_lines: raise ValueError('Text does not fit centered block')
        for n,line in enumerate(lines):
            w=d.textlength(line,font=font(size,bold))
            d.text(((1080-w)/2,y+n*(size+10)),line,font=font(size,bold),fill=color)
        return len(lines)*(size+10)
    centered('MAI MULTE DESPRE OFERTĂ',430,25,bold=True,color=RED)
    y=480
    y+=centered(l['name'],y,54,bold=True,max_lines=2)+38
    description_height=centered(COPY[index],y,46,max_lines=5)
    panel_y=y+description_height+70
    d.rounded_rectangle((40,panel_y,1040,panel_y+740),radius=44,fill='white')
    d.text((80,panel_y+48),'CUM TE AJUTĂ PINFERS',font=font(27,True),fill=RED)
    textblock(d,'Oferte locale. Într-un singur loc.',(80,panel_y+104),65,920,bold=True,max_lines=2)
    rows=[('01','Descoperi locații și oferte pe hartă.'),('02','Vezi prețul, perioada și condițiile.'),('03','Alegi oferta care ți se potrivește.')]
    for n,(num,text) in enumerate(rows):
        yy=panel_y+320+n*120
        d.rounded_rectangle((80,yy,144,yy+64),radius=20,fill='#FFF0ED')
        d.text((91,yy+14),num,font=font(28,True),fill=RED)
        textblock(d,text,(173,yy+8),38,810,max_lines=2)
    footer_h=centered('Verifică disponibilitatea și condițiile complete în aplicație.',panel_y+780,36,color='#6B7280',max_lines=2)
    end_y=panel_y+780+footer_h+12
    shift=max(0,(1920-110-end_y)//2)
    content=im.crop((0,100,1080,end_y))
    d.rectangle((0,100,1080,1920),fill=BG)
    im.paste(content,(0,100+shift))
    return im

def download():
    im,d,brand=base(header=False)
    brand=ImageOps.contain(brand,(800,710))
    im.paste(brand,((1080-brand.width)//2,170+(710-brand.height)//2),brand)
    def center(text,y,size,bold=False,color=INK):
        w=d.textlength(text,font=font(size,bold))
        d.text(((1080-w)//2,y),text,font=font(size,bold),fill=color)
    center('Descarcă Pinfers.',930,78,True)
    center('Găsește oferta în aplicație.',1040,44)
    for name,y in [('google-play',1190),('app-store',1450)]:
        badge=Image.open(ROOT/f'assets/{name}.png').convert('RGBA')
        badge=ImageOps.contain(badge,(620,200))
        im.paste(badge,((1080-badge.width)//2,y),badge)
    center('Disponibilă pe Android și iPhone',1770,32,color='#6B7280')
    return im
