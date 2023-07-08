from pathlib import Path
import re
from typing import List

from rich.progress import track
import yaml
import typer
from pydantic import BaseModel

from acl_miniconf.data import Paper, WORKSHOP, AnthologyAuthor
from acl_miniconf.import_acl2023 import TLDR_LENGTH

CUSTOM_PAPER_YML = {
    Path("workshop-data/DISRPT"): Path("workshop-data/DISRPT/data"),
    Path("workshop-data/LAW"): Path("workshop-data/LAW/inputs"),
    Path("workshop-data/Narrative-Understanding"): Path(
        "workshop-data/Narrative-Understanding/output/inputs/"
    ),
    Path("workshop-data/BEA"): Path("workshop-data/BEA/inputs"),
    Path("workshop-data/IWSLT"): Path("workshop-data/IWSLT/inputs"),
    Path("workshop-data/CODI"): Path("workshop-data/CODI/inputs"),
}


def load_papers(path: Path):
    try:
        with open(path) as f:
            papers = yaml.full_load(f)
    except yaml.scanner.ScannerError:
        lines = []
        with open(path) as f:
            for line in f:
                if "title:" in line:
                    match = re.match(r"(\s+)title: (.+)\n", line)
                    if match is None:
                        raise ValueError()
                    else:
                        spaces = match.group(1)
                        title = match.group(2)
                        lines.append(f'{spaces}title: "{title}"\n')
                elif "abstract:" in line:
                    match = re.match(r"(\s+)abstract: (.+)\n", line)
                    if match is None:
                        raise ValueError()
                    else:
                        spaces = match.group(1)
                        title = match.group(2)
                        # Conference didn't write valid yml and I tried parsing it, don't have time to manually
                        # fix every case, so just stripping abstracts out
                        lines.append(f'{spaces}abstract: ""\n')
                else:
                    lines.append(line)
        fixed_content = "".join(lines)
        papers = yaml.safe_load(fixed_content)
    return papers


class AnthologyWorkshop(BaseModel):
    name: str
    short_name: str
    anthology_venue_id: str
    committee: List[AnthologyAuthor]


def main(
    workshop_data_dir: Path = Path("workshop-data"),
    output_dir: Path = Path("data/acl_2023/data"),
):
    workshops: List[AnthologyWorkshop] = []
    workshop_papers: List[Paper] = []
    for workshop_dir in track(list(workshop_data_dir.glob("*"))):
        short_name = workshop_dir.name
        if workshop_dir in CUSTOM_PAPER_YML:
            workshop_dir = CUSTOM_PAPER_YML[workshop_dir]
        if not (workshop_dir / "papers.yml").exists():
            raise ValueError(f"Workshop papers.yml does not exist for: {workshop_dir}")
        if not (workshop_dir / "conference_details.yml").exists():
            raise ValueError(
                f"Workshop conference_details.yml does not exist for: {workshop_dir}"
            )

        with open(workshop_dir / "conference_details.yml") as f:
            details = yaml.safe_load(f)
            workshop_name = details["event_name"]
            prefix = details["anthology_venue_id"]
            committee: List[AnthologyAuthor] = []
            for p in details["editors"]:
                first_name = p["first_name"]
                last_name = p["last_name"]
                committee.append(
                    AnthologyAuthor(first_name=first_name, last_name=last_name)
                )
            workshops.append(
                AnthologyWorkshop(
                    anthology_venue_id=prefix,
                    name=workshop_name,
                    committee=committee,
                    short_name=short_name,
                ).dict()
            )

        papers = load_papers(workshop_dir / "papers.yml")
        for p in papers:
            workshop_paper_id = p["id"]
            authors = [f"{a['first_name']} {a['last_name']}" for a in p["authors"]]
            if "attributes" in p:
                paper_type = p["attributes"]["paper_type"]
            else:
                paper_type = "long"
            maybe_abstract = p.get("abstract", "")
            workshop_papers.append(
                Paper(
                    id=f"{prefix}_{workshop_paper_id}",
                    title=p["title"],
                    authors=authors,
                    track=workshop_name,
                    paper_type=paper_type,
                    category=WORKSHOP,
                    abstract=maybe_abstract if isinstance(maybe_abstract, str) else "",
                    tldr=maybe_abstract[:TLDR_LENGTH]
                    if isinstance(maybe_abstract, str)
                    else "",
                    event_ids=[short_name],
                    program=WORKSHOP,
                ).dict()
            )
        with open(output_dir / "workshop_papers.yaml", "w") as f:
            yaml.dump(workshop_papers, f)

        with open(output_dir / "workshops.yaml", "w") as f:
            yaml.dump(workshops, f)


if __name__ == "__main__":
    typer.run(main)
