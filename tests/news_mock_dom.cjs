class Node{constructor(doc){this.ownerDocument=doc;this.children=[];this.listeners={};}appendChild(n){this.children.push(n);}replaceChildren(...n){this.children=n;}addEventListener(k,f){this.listeners[k]=f;}removeEventListener(k){delete this.listeners[k];}}
const doc={createElement:()=>new Node(doc)};
module.exports={Node,doc};
