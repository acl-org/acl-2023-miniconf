import json
import os
from typing import List

import numpy as np
import pandas as pd
import umap
from sklearn.neighbors import KDTree
from sklearn.preprocessing import StandardScaler

SPECTER_CMD = """python scripts/embed.py --ids specter.ids --metadata specter_metadata.json --model ./model.tar.gz --output-file specter.jsonl --vocab-dir data/vocab/ --batch-size 16 --cuda-device 0"""


def generate_specter_embeddings(
    paper_ids: List[str], titles: List[str], abstracts: List[str]
):
    metadata = {}

    for paper_id, title, abstract in zip(paper_ids, titles, abstracts):
        metadata[paper_id] = {
            "title": title,
            "abstract": abstract,
            "paper_id": paper_id,
        }

    with open("specter/specter.ids", "w") as f:
        for paper_id in paper_ids:
            f.write(paper_id)
            f.write("\n")

    with open("specter/specter_metadata.json", "w") as f:
        json.dump(metadata, f)

    os.chdir("specter")
    os.system(SPECTER_CMD)
    os.chdir("..")


def generate_umap():
    embeddings = []
    idx_to_id = {}

    with open("specter/specter.jsonl") as f:
        for i, line in enumerate(f):
            data = json.loads(line)

            embeddings.append(data["embedding"])
            idx_to_id[i] = data["paper_id"]

    embeddings = np.array(embeddings)
    reducer = umap.UMAP()

    scaled_data = StandardScaler().fit_transform(embeddings)

    result = reducer.fit_transform(scaled_data)

    projections = []
    for i, row in enumerate(result):
        projections.append({"id": idx_to_id[i], "pos": [float(x) for x in row]})

    with open("paper_projections.json", "w") as f:
        json.dump(projections, f, indent=2)


def generate_recommendations():
    embeddings = []
    idx_to_id = {}

    with open("specter/specter.jsonl") as f:
        for i, line in enumerate(f):
            data = json.loads(line)

            embeddings.append(data["embedding"])
            idx_to_id[i] = data["paper_id"]

    X = np.array(embeddings)
    tree = KDTree(X)

    dist, ind = tree.query(X, k=6)

    result = {}
    for i, e in enumerate(ind):
        recs = [idx_to_id[idx] for idx in e[1:]]
        result[idx_to_id[i]] = recs

    with open("paper_recs.json", "w") as f:
        json.dump(result, f)


def main():
    main_papers = pd.read_csv("main_papers.csv")
    demo_papers = pd.read_csv("demo_papers.csv")

    paper_ids = main_papers["UID"].tolist() + demo_papers["UID"].tolist()
    titles = main_papers["title"].tolist() + demo_papers["title"].tolist()
    abstracts = main_papers["abstract"].tolist() + demo_papers["abstract"].tolist()

    generate_specter_embeddings(paper_ids, titles, abstracts)
    generate_umap()
    generate_recommendations()


if __name__ == "__main__":
    main()
