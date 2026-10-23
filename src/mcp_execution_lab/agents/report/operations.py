import html
import re

from ..common.models import Fact, NeedsInput, Unsupported
from ..common.operations import render_text
from .models import Details


def evidence_facts(values, refs):
    facts, warnings, source_map = [], [], {}
    for index, (value, ref) in enumerate(zip(values, refs, strict=True)):
        if not isinstance(value, dict) or not isinstance(value.get("facts"), list):
            raise NeedsInput("A report requires registered structured findings with checked facts.")
        if value.get("outcome", "COMPLETED") != "COMPLETED":
            warnings.append("An input describes incomplete work; its limits must remain visible.")
        for raw in value["facts"]:
            fact = Fact.model_validate(raw)
            key = f"source_{index}_{fact.id}"
            if key in source_map:
                raise NeedsInput("Evidence contains repeated fact IDs.")
            facts.append(fact.model_copy(update={"id": key}))
            source_map[key] = ref.id
        warnings.extend(value.get("warnings", []))
    if not facts:
        raise NeedsInput("No checked facts were supplied for the report.")
    return facts, warnings, source_map


def escaped(text):
    return re.sub(r"([\\`*\[\]#_])", r"\\\1", html.escape(text, quote=False))


def render(recipe, facts, sources, warnings, charts, style):
    if recipe.question:
        raise NeedsInput(recipe.question)
    known = {fact.id for fact in facts}
    title = render_text(recipe.title, facts)
    lines, claims = ["# " + escaped(title), ""], []
    for index, section in enumerate(recipe.sections):
        if not section.fact_ids or not set(section.fact_ids) <= known:
            raise NeedsInput("A report section must cite known evidence facts.")
        lines += ["## " + escaped(render_text(section.title, facts)), ""]
        for paragraph in section.paragraphs:
            used = set(re.findall(r"\{\{fact:([a-zA-Z0-9_]+)\}\}", paragraph))
            if not used <= set(section.fact_ids):
                raise NeedsInput("A numeric claim is missing its section evidence link.")
            lines += [escaped(render_text(paragraph, facts)), ""]
            claims.append(
                {
                    "section": str(index),
                    "text": paragraph,
                    "fact_ids": section.fact_ids,
                    "evidence_ids": sorted({sources[key] for key in section.fact_ids}),
                }
            )
    if warnings or recipe.limitations:
        lines += ["## Limits", ""]
        lines += ["- " + escaped(render_text(text, facts)) for text in recipe.limitations]
        # These warnings come from checked prior workers, not the draft; keep them verbatim.
        lines += ["- " + escaped(text) for text in dict.fromkeys(warnings)]
        lines.append("")
    for ref in charts:
        if ref.kind != "png":
            raise Unsupported("Reports currently embed registered PNG charts only.")
        lines += [f"![Saved chart]({ref.id}.png)", ""]
    lines += ["## Sources", ""]
    lines += [f"- `{key}`" for key in sorted(set(sources.values()))]
    text = "\n".join(lines)
    if len(text) > style.max_characters:
        raise Unsupported("The report exceeds its configured length allowance.")
    return text, Details(
        title=title,
        claim_sources=claims,
        input_evidence_ids=sorted(set(sources.values())),
        character_count=len(text),
    )
