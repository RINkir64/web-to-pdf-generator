import zipfile
import uuid
import datetime

class EpubBuilder:
    def __init__(self, title, language="ja"):
        self.title = title
        self.language = language
        self.identifier = str(uuid.uuid4())
        self.chapters = []
        self.images = {}

    def add_chapter(self, file_name, title, content):
        self.chapters.append((file_name, title, content))

    def add_image(self, file_name, content, media_type):
        self.images[file_name] = (content, media_type)

    def write(self, output_path):
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # mimetype must be uncompressed and the very first file
            try:
                zf.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
            except TypeError:
                zf.writestr('mimetype', 'application/epub+zip')

            # META-INF/container.xml
            container_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>'''
            zf.writestr('META-INF/container.xml', container_xml)

            # OEBPS/content.opf
            items_xml = []
            itemrefs_xml = []
            
            items_xml.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
            items_xml.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
            items_xml.append('<item id="style_nav" href="style/nav.css" media-type="text/css"/>')
            
            for i, (fname, _, _) in enumerate(self.chapters, 1):
                iid = f"chap_{i}"
                items_xml.append(f'<item id="{iid}" href="{fname}" media-type="application/xhtml+xml"/>')
                itemrefs_xml.append(f'<itemref idref="{iid}"/>')
                
            for i, (fname, (_, mtype)) in enumerate(self.images.items(), 1):
                iid = f"img_{i}"
                items_xml.append(f'<item id="{iid}" href="{fname}" media-type="{mtype}"/>')
                
            items_str = '\n        '.join(items_xml)
            itemrefs_str = '\n        '.join(itemrefs_xml)
            last_modified = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            
            opf_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>{self.title}</dc:title>
        <dc:language>{self.language}</dc:language>
        <dc:identifier id="pub-id">urn:uuid:{self.identifier}</dc:identifier>
        <meta property="dcterms:modified">{last_modified}</meta>
    </metadata>
    <manifest>
        {items_str}
    </manifest>
    <spine toc="ncx">
        {itemrefs_str}
    </spine>
</package>'''
            zf.writestr('OEBPS/content.opf', opf_xml)

            # OEBPS/nav.xhtml
            nav_li = []
            for fname, ctitle, _ in self.chapters:
                nav_li.append(f'<li><a href="{fname}">{ctitle}</a></li>')
            nav_li_str = '\n            '.join(nav_li)
            
            nav_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>{self.title}</title></head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>Table of Contents</h1>
        <ol>
            {nav_li_str}
        </ol>
    </nav>
</body>
</html>'''
            zf.writestr('OEBPS/nav.xhtml', nav_xhtml)

            # OEBPS/toc.ncx
            nav_p_li = []
            for i, (fname, ctitle, _) in enumerate(self.chapters, 1):
                nav_p_li.append(f'''<navPoint id="navPoint-{i}" playOrder="{i}">
            <navLabel><text>{ctitle}</text></navLabel>
            <content src="{fname}"/>
        </navPoint>''')
            nav_p_str = '\n        '.join(nav_p_li)
            
            toc_ncx = f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <head>
        <meta name="dtb:uid" content="urn:uuid:{self.identifier}"/>
        <meta name="dtb:depth" content="1"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
    </head>
    <docTitle><text>{self.title}</text></docTitle>
    <navMap>
        {nav_p_str}
    </navMap>
</ncx>'''
            zf.writestr('OEBPS/toc.ncx', toc_ncx)

            # style
            zf.writestr('OEBPS/style/nav.css', "body { font-family: -apple-system, sans-serif; }")
            
            # chapters
            for fname, _, content in self.chapters:
                content_str = content if isinstance(content, str) else content.decode('utf-8')
                if 'xmlns="http://www.w3.org/1999/xhtml"' not in content_str:
                    content_str = content_str.replace('<html', '<html xmlns="http://www.w3.org/1999/xhtml"', 1)
                
                if not content_str.strip().startswith('<?xml'):
                    content_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + content_str
                    
                zf.writestr(f"OEBPS/{fname}", content_str.encode('utf-8'))
                
            # images
            for fname, (content, _) in self.images.items():
                if isinstance(content, str):
                    content = content.encode('utf-8')
                zf.writestr(f"OEBPS/{fname}", content)
