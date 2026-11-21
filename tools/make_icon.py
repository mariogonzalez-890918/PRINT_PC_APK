"""Rasterize the application's existing geometric printer mark as a Windows icon."""
from pathlib import Path
from PIL import Image, ImageDraw

root=Path(__file__).resolve().parents[1]
scale=4
image=Image.new('RGBA',(256*scale,256*scale),(0,0,0,0))
draw=ImageDraw.Draw(image)
def box(coords,color,radius=0):
    xy=tuple(round(x*256/108*scale) for x in coords)
    if radius:draw.rounded_rectangle(xy,radius=round(radius*256/108*scale),fill=color)
    else:draw.rectangle(xy,fill=color)
box((0,0,107,107),'#123458',22)
for rect in [(30,19,78,43),(22,41,86,79),(39,66,69,90)]:box(rect,'white')
box((34,61,74,65),'#123458')
box((34,65,38,80),'#123458')
box((70,65,74,80),'#123458')
box((73,47,80,54),'#47c6cf')
image=image.resize((256,256),Image.Resampling.LANCZOS)
image.save(root/'pc'/'app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
image.save(root/'pc'/'app.png')
