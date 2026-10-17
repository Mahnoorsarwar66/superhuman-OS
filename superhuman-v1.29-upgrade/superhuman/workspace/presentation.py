"""Small, escaped text renderer; no arbitrary HTML, images, scripts or raw links."""
import html,re

def rich(value):
    value=str(value or '')[:60000];out=[];listing=False;code=False
    def inline(s):
        s=html.escape(s,quote=True)
        s=re.sub(r'\*\*([^*\n]+)\*\*',r'<strong>\1</strong>',s)
        s=re.sub(r'`([^`\n]+)`',r'<code>\1</code>',s)
        return s
    for line in value.splitlines():
        if line.startswith('```'):
            if listing:out.append('</ul>');listing=False
            out.append('</code></pre>' if code else '<pre><code>');code=not code;continue
        if code:out.append(html.escape(line)+'\n');continue
        item=re.match(r'^\s*(?:[-*]|\d+[.)])\s+(.+)',line)
        if item:
            if not listing:out.append('<ul>');listing=True
            out.append('<li>'+inline(item.group(1))+'</li>');continue
        if listing:out.append('</ul>');listing=False
        heading=re.match(r'^#{1,6}\s+(.+)',line)
        out.append('<h3>'+inline(heading.group(1))+'</h3>' if heading else '<p>'+inline(line)+'</p>' if line.strip() else '')
    if listing:out.append('</ul>')
    if code:out.append('</code></pre>')
    return ''.join(out)
