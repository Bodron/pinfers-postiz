"""Render an offline Pinfers preview. Never writes to Pinfers or publishes posts."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / 'outputs'
OUT.mkdir(exist_ok=True)
DATA = []
RED = '#C20302'
INK = '#212326'
BG = '#EAF0F6'
FONT = str(ROOT/'assets/fonts/Outfit.ttf')

def font(size, bold=False):
    result=ImageFont.truetype(FONT,size)
    result.set_variation_by_axes([700 if bold else 400])
    return result

def wrap(draw, text, size, width, bold=False):
    lines, line = [], ''
    for word in text.split():
        candidate = (line + ' ' + word).strip()
        if draw.textlength(candidate, font=font(size,bold)) > width and line:
            lines.append(line); line = word
        else: line = candidate
    if line: lines.append(line)
    return lines

def textblock(draw, text, xy, size, width, color=INK, bold=False, max_lines=3):
    lines = wrap(draw, text, size, width, bold)
    while len(lines) > max_lines and size > 24:
        size -= 2; lines = wrap(draw, text, size, width, bold)
    if len(lines)>max_lines: raise ValueError('Text exceeds layout: '+text)
    for n,line in enumerate(lines):
        draw.text((xy[0],xy[1]+n*(size+10)),line,font=font(size,bold),fill=color)
    return len(lines)*(size+10)

def dt(raw):
    return datetime.fromisoformat(raw.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Bucharest'))

def money(value):
    return f'{value:,.2f}'.replace(',',' ').replace('.',',').removesuffix(',00')

def rounded_asset(asset, radius=36):
    asset=asset.convert('RGBA')
    mask=Image.new('L',asset.size,0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,asset.width-1,asset.height-1),radius=radius,fill=255)
    from PIL import ImageChops
    asset.putalpha(ImageChops.multiply(asset.getchannel('A'),mask))
    return asset

def render(i, index, height):
    o,l=i['offer'],i['location']
    im=Image.new('RGB',(1080,height),BG); d=ImageDraw.Draw(im)
    vertical=height>1400
    brand=Image.open(ROOT/'assets'/'pinfers-logo.png').convert('RGBA')
    bounds=brand.getchannel('A').getbbox()
    if bounds: brand=brand.crop(bounds)
    brand=ImageOps.contain(brand,(78,68))
    im.paste(brand,(36+(78-brand.width)//2,12+(68-brand.height)//2),brand)
    name_size=34
    while d.textlength(l['name'],font=font(name_size,True))>840: name_size-=2
    name_width=int(d.textlength(l['name'],font=font(name_size,True)))+48
    d.rounded_rectangle((132,15,132+name_width,80),radius=24,fill='white')
    d.text((156,29),l['name'],font=font(name_size,True),fill=INK)
    hero_top=110
    product=Image.open(ROOT/'assets'/f'{index}-offer.img').convert('RGBA')
    # Remove only near-white outer margins of product photos to enlarge the subject.
    from PIL import ImageChops
    rgb=product.convert('RGB')
    diff=ImageChops.difference(rgb,Image.new('RGB',rgb.size,'white'))
    bounds=diff.convert('L').point(lambda p: 255 if p>25 else 0).getbbox()
    if bounds:
        x0,y0,x1,y1=bounds; pad=24
        product=product.crop((max(0,x0-pad),max(0,y0-pad),min(product.width,x1+pad),min(product.height,y1+pad)))
    product=ImageOps.contain(product,(988,height-(810 if vertical else 610)))
    product=rounded_asset(product,40)
    # Keep the photo and its price panel together; balance margins around the group.
    panel_height=580 if vertical else 425
    group_height=product.height+18+panel_height
    group_top=hero_top+max(12,(height-hero_top-100-group_height)//2)
    im.paste(product,((1080-product.width)//2,group_top),product)
    sheet_y=group_top+product.height+18
    panel_bottom=sheet_y+panel_height
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((32,sheet_y,1048,panel_bottom),radius=36,fill='white')
    title_y=sheet_y+26
    size=60 if vertical else 42
    while len(wrap(d,o['title'],size,968,True))>2 and size>24: size-=2
    textblock(d,o['title'],(56,title_y),size,968,bold=True,max_lines=2)
    currency=o.get('currency','RON')
    parts=o.get('items') or []
    original=None
    if parts and all(isinstance(x.get('price'),(int,float)) and (x.get('currency') or currency)==currency for x in parts):
        total=sum(x['price']*x.get('qty',1) for x in parts)
        if total>o['price']: original=total
    price_y=sheet_y+(190 if vertical else 146)
    if original is not None:
        old=money(original)+' '+currency
        d.text((56,price_y),old,font=font(38),fill='#8A8E95')
        box=d.textbbox((56,price_y),old,font=font(38))
        strike=(box[1]+box[3])//2
        d.line((box[0]-3,strike,box[2]+3,strike),fill='#8A8E95',width=3)
        percent=(original-o['price'])/original*100
        # Round down to a whole percentage so the displayed saving is never overstated.
        from decimal import Decimal, ROUND_FLOOR
        percent_decimal=(Decimal(str(original))-Decimal(str(o['price'])))/Decimal(str(original))*100
        label=str(int(percent_decimal.to_integral_value(rounding=ROUND_FLOOR)))
        badge=f'−{label}%'
        badge_size=52 if vertical else 44
        badge_w=int(d.textlength(badge,font=font(badge_size,True)))+48
        d.rounded_rectangle((1024-badge_w,price_y-10,1024,price_y+65),radius=24,fill='#EDF1F5')
        d.text((1048-badge_w,price_y),badge,font=font(badge_size,True),fill='#111111')
    price=money(o['price'])+' '+o.get('currency','RON')
    price_size=112 if vertical else 86
    while d.textlength(price,font=font(price_size,True))>968: price_size-=2
    d.text((51,price_y+(65 if vertical else 49)),price,font=font(price_size,True),fill=RED)
    start,end=dt(o['startDate']),dt(o['endDate'])
    d.text((56,panel_bottom-(150 if vertical else 120)),f'{start:%d.%m.%Y} – {end:%d.%m.%Y} · până la {end:%H:%M}',font=font(30 if vertical else 27,True),fill=INK)
    days=o.get('validDays') or []
    daynames=['Du','Lu','Ma','Mi','Jo','Vi','Sâ']
    restrictions=[]
    if days and len(days)<7: restrictions.append('Zile: '+', '.join(daynames[x] for x in sorted(days)))
    slots=o.get('validTimeSlots') or []
    if slots: restrictions.append(' / '.join(s['startTime']+'–'+s['endTime'] for s in slots))
    if restrictions: textblock(d,' · '.join(restrictions),(56,panel_bottom-(108 if vertical else 82)),28 if vertical else 24,968,color='#6B7280',max_lines=1)
    d.line((56,panel_bottom-57,1024,panel_bottom-57),fill='#EDEDED',width=2)
    d.text((56,panel_bottom-42),'Oferta și condițiile complete în aplicația Pinfers',font=font(23),fill='#6B7280')
    d.text((957,panel_bottom-42),'',font=font(23,True),fill=RED)
    return im
