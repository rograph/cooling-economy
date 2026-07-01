import cairosvg
W,H=1200,630
svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Arial, Helvetica, sans-serif">
<defs>
 <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0c1636"/><stop offset="1" stop-color="#070c1a"/></linearGradient>
 <linearGradient id="grad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f6c945"/><stop offset="0.52" stop-color="#ff2e74"/><stop offset="1" stop-color="#2fe0d8"/></linearGradient>
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<circle cx="1080" cy="90" r="230" fill="url(#grad)" opacity="0.14"/>
<circle cx="150" cy="600" r="200" fill="#2fe0d8" opacity="0.08"/>
<rect x="70" y="86" width="150" height="10" rx="5" fill="url(#grad)"/>
<text x="70" y="150" fill="#95a6cc" font-size="26" font-weight="700" letter-spacing="4">COOLING ECONOMY &#183; WORLD CUP 2026</text>
<text x="70" y="245" fill="#ffffff" font-size="76" font-weight="800">Do hydration breaks</text>
<text x="70" y="330" fill="#ffffff" font-size="76" font-weight="800">change the game?</text>
<text x="70" y="400" fill="#c3cfeb" font-size="30" font-weight="500">Before vs after every break, across the whole tournament.</text>
<rect x="70" y="452" width="560" height="66" rx="14" fill="#101a38" stroke="#26345c"/>
<rect x="70" y="452" width="8" height="66" rx="4" fill="url(#grad)"/>
<text x="100" y="494" fill="#f6c945" font-size="27" font-weight="800">Explore the data. Cast your vote.</text>
<text x="70" y="575" fill="#95a6cc" font-size="25" font-weight="600">Live and interactive, updated every match &#183; Rodolfo López</text>
</svg>'''
open("card.svg","w").write(svg)
cairosvg.svg2png(bytestring=svg.encode(),write_to="cooling_economy_card.png",output_width=1200,output_height=630)
print("card png written")
