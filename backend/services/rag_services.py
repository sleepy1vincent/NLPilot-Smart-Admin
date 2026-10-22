import os
import ollama
import chromadb

_client=None
_collections=None
base_dir=os.path.dirname(os.path.abspath(__file__))
rag_path=os.path.join(base_dir,"..","rag_store")

def _get():
    global _client,_collections
    if _collections is None:
        _client=chromadb.PersistentClient(path=rag_path)
        _collections=_client.get_or_create_collection(name="product_v2",
                                                      embedding_function=None,
                                                      metadata={"hnsw:space": "cosine"},)
    return _collections
def _doc(p:dict)->str:
    """商品 → 供 embedding 的文本。空字段自动跳过"""
    tags=(p.get("tags")or"").replace(","," ")
    parts=[p.get("name"),p.get("category"),tags,p.get("description")]
    return  " ".join(str(x).strip() for x in parts if x and str(x).strip())
def _embed(text:str):
    return ollama.embeddings(model="bge-m3",prompt=text)["embedding"]
def init_product(products:list[dict]):
    """products 每项需要 id/name，可选 category/tags/description"""
    col=_get()
    if not products:
        return
    docs = [_doc(p) for p in products]
    col.upsert(
        ids=[str(p["id"])for p in products],
        documents=docs,
        embeddings=[_embed(d)for d in docs],
        metadatas=[{"category": p.get("category") or ""} for p in products],
    )
def search_products(query:str,top_k:int=3):
    col=_get()
    if col.count()==0:
        return[]
    r=col.query(n_results=min(top_k,col.count()),
                     query_embeddings=[_embed(query)],
                     include=["distances"],
    )
    ids, dists = r["ids"][0], r["distances"][0]
    return [(i, d) for i, d in zip(ids, dists)]
def upsert_product(p: dict):
    """单个商品同步（新增/修改后调用）"""
    col = _get()
    doc = _doc(p)
    col.upsert(ids=[str(p["id"])], documents=[doc],
               embeddings=[_embed(doc)],
               metadatas=[{"category": p.get("category") or ""}])
def delete_products(ids: list[int]):
    if not ids:
        return
    _get().delete(ids=[str(i) for i in ids])
def find_similar(product_id: int, top_k: int = 5):
    """找相似商品：用该商品自己的向量做查询"""
    col = _get()
    got = col.get(ids=[str(product_id)], include=["embeddings"])
    if not got["embeddings"]:
        return []
    r = col.query(query_embeddings=[got["embeddings"][0]],
                  n_results=top_k + 1, include=["distances"])
    return [(i, d) for i, d in zip(r["ids"][0], r["distances"][0])
            if i != str(product_id)][:top_k]