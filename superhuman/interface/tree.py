"""Small, dependency-free fragment tree used only on trusted server templates."""
from html import escape,unescape
from html.parser import HTMLParser
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
class Node:
    def __init__(self,tag='',attrs=(),raw='',children=None):
        self.tag=tag;self.attrs=dict(attrs);self.raw=raw;self.children=children or []
    def html(self):
        if not self.tag:return ''.join(c.html() if isinstance(c,Node) else c for c in self.children)
        opening=self.raw or '<'+self.tag+''.join(' '+k+('="'+escape(str(v),quote=True)+'"' if v is not None else '') for k,v in self.attrs.items())+'>'
        return opening+('' if self.tag in VOID else ''.join(c.html() if isinstance(c,Node) else c for c in self.children)+'</'+self.tag+'>')
    def text(self):return unescape(''.join(c.text() if isinstance(c,Node) else c for c in self.children))
    def find(self,tag=None,**attrs):
        found=[]
        for c in self.children:
            if isinstance(c,Node):
                if (tag is None or c.tag==tag) and all(c.attrs.get(k)==v for k,v in attrs.items()):found.append(c)
                found.extend(c.find(tag,**attrs))
        return found
    def has_class(self,name):return name in (self.attrs.get('class') or '').split()
    def set(self,key,value):self.attrs[key]=value;self.raw='';return self
    def replace_text(self,value):self.children=[escape(value)];return self
class Parser(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=False);self.root=Node();self.stack=[self.root]
    def handle_starttag(self,tag,attrs):
        node=Node(tag,attrs,self.get_starttag_text());self.stack[-1].children.append(node)
        if tag not in VOID:self.stack.append(node)
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs);self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):self.stack[-1].children.append(data)
    def handle_entityref(self,name):self.stack[-1].children.append('&'+name+';')
    def handle_charref(self,name):self.stack[-1].children.append('&#'+name+';')
    def handle_comment(self,data):self.stack[-1].children.append('<!--'+data+'-->')
def parse(body):
    parser=Parser();parser.feed(body);parser.close();return parser.root

def html(nodes):return ''.join(n.html() if isinstance(n,Node) else n for n in nodes)
def text(node):return node.text().strip() if isinstance(node,Node) else unescape(node).strip()
