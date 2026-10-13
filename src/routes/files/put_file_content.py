# src/routes/files/put_file_content.py
import yaml
from fastapi import HTTPException

from src.core.logging_config import logger
from src.core.obsidian_processor import is_summarizable_path
from src.navigation.vault_navigation import (
    FRONTMATTER_PATTERN,
    VaultPathError,
    _read_md,
    _resolve,
    _vault_path,
    _vault_root,
)
from src.routes.files import router
from src.routes.files.get_file_content import _load_file_response
from src.schemas.file_schema import UpdateFileRequest, UpdateFileResponse


@router.put("/content", response_model=UpdateFileResponse)
def put_file_content(body: UpdateFileRequest):
    """Speichert den bearbeiteten Inhalt einer Datei im Vault."""
    root = _vault_root().resolve()


    try:
        resolved = _resolve(body.path, root, expect="file")
    except VaultPathError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"'{body.path}' ist keine Datei.")

    if not is_summarizable_path(resolved):
        raise HTTPException(
            status_code=400,
            detail=f"Datei '{resolved.name}' ist eine Systemdatei und kann nicht bearbeitet werden.",
        )

    # Bestehendes Frontmatter lesen
    existing_fm, _ = _read_md(resolved)

    content = body.content
    match = FRONTMATTER_PATTERN.match(content)

    if match:
        # Benutzer hat Text mit Frontmatter-Header editiert
        try:
            user_fm = yaml.safe_load(match.group(1)) or {}
            # Falls ai_summary im alten fm war, aber im user_fm nicht vorkommt, beibehalten
            if "ai_summary" not in user_fm and existing_fm.get("ai_summary"):
                user_fm["ai_summary"] = existing_fm["ai_summary"]
            parsed_body = match.group(2).strip()
            fm_yaml = yaml.dump(user_fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
            new_text = f"---\n{fm_yaml}---\n{parsed_body}\n"
        except yaml.YAMLError:
            # Falls YAML fehlerhaft formatiert ist, schreiben wir den Inhalt direkt
            new_text = content.rstrip() + "\n"
    else:
        # Benutzer hat nur den Body (ohne Frontmatter) editiert
        body_text = content.strip()
        if existing_fm:
            fm_yaml = yaml.dump(existing_fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
            new_text = f"---\n{fm_yaml}---\n{body_text}\n"
        else:
            new_text = body_text + "\n"

    try:
        resolved.write_text(new_text, encoding="utf-8")
        rel_path = _vault_path(resolved, root)
        logger.info(f"[Mutation] Datei manuell im Frontend bearbeitet: {rel_path}")
        updated_file = _load_file_response(rel_path)

        return UpdateFileResponse(
            path=rel_path,
            success=True,
            message=f"Datei '{resolved.name}' wurde erfolgreich gespeichert.",
            file=updated_file,
        )
    except Exception as e:
        logger.error(f"[Mutation] Fehler beim Speichern von {resolved}: {e}")
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern: {str(e)}")
