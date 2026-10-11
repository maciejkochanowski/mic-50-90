"""Offline publication typography shared by the desktop and HTML renderers."""
from base64 import b64encode
from functools import lru_cache
import json
from pathlib import Path
import re

ASSET_DIR = Path(__file__).parent / 'gui_assets'
FONT_DIR = ASSET_DIR / 'fonts'
FONT_FILES = json.loads((FONT_DIR / 'FONT_MANIFEST.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=4)
def font_faces(*, embedded=True, charts=False):
    faces=[]
    for name, info in FONT_FILES.items():
        if charts and info['family'] != 'DejaVu Sans':
            continue
        url = ('data:font/woff;base64,'+b64encode((FONT_DIR/name).read_bytes()).decode('ascii')
               if embedded else '/assets/fonts/'+name)
        faces.append('@font-face{font-family:"'+info['family']+'";font-style:'+info['style']+
                     ';font-weight:'+str(info['weight'])+';font-display:block;src:url("'+url+'") format("woff")}')
    return ''.join(faces)


@lru_cache(maxsize=2)
def stylesheet(*, embedded=True):
    return font_faces(embedded=embedded)+(ASSET_DIR/'typography.css').read_text(encoding='utf-8')


def portable_svg(svg):
    """A downloaded SVG carries its own chart fonts, independent of the HTML."""
    if 'data-mic-fonts=' in svg:
        return svg
    head, tail = svg.split('>',1)
    if 'xmlns=' not in head:
        head += ' xmlns="http://www.w3.org/2000/svg"'
    return head+'><defs><style data-mic-fonts="embedded">'+font_faces(charts=True)+\
        'text{font-family:"DejaVu Sans",sans-serif}</style></defs>'+tail


def html_with_typography(text):
    """Attach offline typography and the same controls used by the application."""
    marker='<style id="mic-typography">'
    if marker not in text:
        style=marker+stylesheet()+'</style>'
        if '</head>' in text:
            text=text.replace('</head>',style+'</head>',1)
        else:
            text=re.sub(r'</style>',lambda m:m[0]+style,text,count=1)
    if 'id="mic-report-controls"' not in text:
        # Only packaged code is executable. User content is escaped by the renderers.
        controls='<style id="mic-report-print">'+(ASSET_DIR/'report_print.css').read_text(encoding='utf-8')+'</style>'
        controls+='<script id="mic-report-controls">'+(ASSET_DIR/'report_view.js').read_text(encoding='utf-8')+'</script>'
        text=text.replace('</body>',controls+'</body>',1) if '</body>' in text else text+controls
    return text


def display_status(layer, *, requested=True):
    """Present request intent without changing machine-readable scientific status."""
    if not requested:
        return 'Not requested'
    status=layer.get('status','unavailable')
    if layer.get('calculation_assessment') == 'numerically_unresolved' or status in ('timeout','interrupted','incomplete'):
        return 'Calculation incomplete'
    return {'supported':'Condition met','contradicted':'Condition not met',
            'undetermined':'Not enough information','unavailable':'Unavailable',
            'refused':'Analysis refused','available':'Possible share',
            'ok':'Available','baseline_retained':'Conservative bounds retained',
            'not_requested':'Not requested'}.get(status,status.replace('_',' ').capitalize())
