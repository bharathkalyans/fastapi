import json
<<<<<<< HEAD
import logging
=======
>>>>>>> feat/5060-automatic-language-names
import os
import re
import shutil
import subprocess
from functools import lru_cache
from http.server import HTTPServer, SimpleHTTPRequestHandler
from importlib import metadata
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import mkdocs.commands.build
import mkdocs.commands.serve
import mkdocs.config
import mkdocs.utils
import typer
import yaml
from jinja2 import Template

logging.basicConfig(level=logging.INFO)

app = typer.Typer()

mkdocs_name = "mkdocs.yml"

missing_translation_snippet = """
{!../../../docs/missing-translation.md!}
"""

docs_path = Path("docs")
en_docs_path = Path("docs/en")
en_config_path: Path = en_docs_path / mkdocs_name
site_path = Path("site").absolute()
build_site_path = Path("site_build").absolute()


@lru_cache()
def is_mkdocs_insiders() -> bool:
    version = metadata.version("mkdocs-material")
    return "insiders" in version


def get_en_config() -> Dict[str, Any]:
    return mkdocs.utils.yaml_load(en_config_path.read_text(encoding="utf-8"))


def get_lang_paths() -> List[Path]:
    return sorted(docs_path.iterdir())


def lang_callback(lang: Optional[str]) -> Union[str, None]:
    if lang is None:
        return None
    if not lang.isalpha() or len(lang) != 2:
        typer.echo("Use a 2 letter language code, like: es")
        raise typer.Abort()
    lang = lang.lower()
    return lang


def complete_existing_lang(incomplete: str):
    lang_path: Path
    for lang_path in get_lang_paths():
        if lang_path.is_dir() and lang_path.name.startswith(incomplete):
            yield lang_path.name


@app.callback()
def callback() -> None:
    if is_mkdocs_insiders():
        os.environ["INSIDERS_FILE"] = "../en/mkdocs.insiders.yml"
    # For MacOS with insiders and Cairo
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = "/opt/homebrew/lib"


@app.command()
def new_lang(lang: str = typer.Argument(..., callback=lang_callback)):
    """
    Generate a new docs translation directory for the language LANG.

    LANG should be a 2-letter language code, like: en, es, de, pt, etc.
    """
    new_path: Path = Path("docs") / lang
    if new_path.exists():
        typer.echo(f"The language was already created: {lang}")
        raise typer.Abort()
    new_path.mkdir()
    new_config_path: Path = Path(new_path) / mkdocs_name
    new_config_path.write_text("INHERIT: ../en/mkdocs.yml\n", encoding="utf-8")
    new_config_docs_path: Path = new_path / "docs"
    new_config_docs_path.mkdir()
    en_index_path: Path = en_docs_path / "docs" / "index.md"
    new_index_path: Path = new_config_docs_path / "index.md"
    en_index_content = en_index_path.read_text(encoding="utf-8")
    new_index_content = f"{missing_translation_snippet}\n\n{en_index_content}"
    new_index_path.write_text(new_index_content, encoding="utf-8")
    typer.secho(f"Successfully initialized: {new_path}", color=typer.colors.GREEN)
    update_languages()


@app.command()
def build_lang(
    lang: str = typer.Argument(
        ..., callback=lang_callback, autocompletion=complete_existing_lang
    )
) -> None:
    """
    Build the docs for a language.
    """
    insiders_env_file = os.environ.get("INSIDERS_FILE")
    print(f"Insiders file {insiders_env_file}")
    if is_mkdocs_insiders():
        print("Using insiders")
    lang_path: Path = Path("docs") / lang
    if not lang_path.is_dir():
        typer.echo(f"The language translation doesn't seem to exist yet: {lang}")
        raise typer.Abort()
    typer.echo(f"Building docs for: {lang}")
    build_site_dist_path = build_site_path / lang
    if lang == "en":
        dist_path = site_path
        # Don't remove en dist_path as it might already contain other languages.
        # When running build_all(), that function already removes site_path.
        # All this is only relevant locally, on GitHub Actions all this is done through
        # artifacts and multiple workflows, so it doesn't matter if directories are
        # removed or not.
    else:
        dist_path = site_path / lang
        shutil.rmtree(dist_path, ignore_errors=True)
    current_dir = os.getcwd()
    os.chdir(lang_path)
    shutil.rmtree(build_site_dist_path, ignore_errors=True)
    subprocess.run(["mkdocs", "build", "--site-dir", build_site_dist_path], check=True)
    shutil.copytree(build_site_dist_path, dist_path, dirs_exist_ok=True)
    os.chdir(current_dir)
    typer.secho(f"Successfully built docs for: {lang}", color=typer.colors.GREEN)


index_sponsors_template = """
{% if sponsors %}
{% for sponsor in sponsors.gold -%}
<a href="{{ sponsor.url }}" target="_blank" title="{{ sponsor.title }}"><img src="{{ sponsor.img }}"></a>
{% endfor -%}
{%- for sponsor in sponsors.silver -%}
<a href="{{ sponsor.url }}" target="_blank" title="{{ sponsor.title }}"><img src="{{ sponsor.img }}"></a>
{% endfor %}
{% endif %}
"""


def generate_readme_content() -> str:
    en_index = en_docs_path / "docs" / "index.md"
    content = en_index.read_text("utf-8")
    match_start = re.search(r"<!-- sponsors -->", content)
    match_end = re.search(r"<!-- /sponsors -->", content)
    sponsors_data_path = en_docs_path / "data" / "sponsors.yml"
    sponsors = mkdocs.utils.yaml_load(sponsors_data_path.read_text(encoding="utf-8"))
    if not (match_start and match_end):
        raise RuntimeError("Couldn't auto-generate sponsors section")
    pre_end = match_start.end()
    post_start = match_end.start()
    template = Template(index_sponsors_template)
    message = template.render(sponsors=sponsors)
    pre_content = content[:pre_end]
    post_content = content[post_start:]
    new_content = pre_content + message + post_content
    return new_content


@app.command()
def generate_readme() -> None:
    """
    Generate README.md content from main index.md
    """
    typer.echo("Generating README")
    readme_path = Path("README.md")
    new_content = generate_readme_content()
    readme_path.write_text(new_content, encoding="utf-8")


@app.command()
def verify_readme() -> None:
    """
    Verify README.md content from main index.md
    """
    typer.echo("Verifying README")
    readme_path = Path("README.md")
    generated_content = generate_readme_content()
    readme_content = readme_path.read_text("utf-8")
    if generated_content != readme_content:
        typer.secho(
            "README.md outdated from the latest index.md", color=typer.colors.RED
        )
        raise typer.Abort()
    typer.echo("Valid README ✅")


@app.command()
def build_all() -> None:
    """
    Build mkdocs site for en, and then build each language inside, end result is located
    at directory ./site/ with each language inside.
    """
    update_languages()
    shutil.rmtree(site_path, ignore_errors=True)
    langs = [lang.name for lang in get_lang_paths() if lang.is_dir()]
    cpu_count = os.cpu_count() or 1
    process_pool_size = cpu_count * 4
    typer.echo(f"Using process pool size: {process_pool_size}")
    with Pool(process_pool_size) as p:
        p.map(build_lang, langs)


@app.command()
def update_languages() -> None:
    """
    Update the mkdocs.yml file Languages section including all the available languages.
    """
    update_config()


@app.command()
def serve() -> None:
    """
    A quick server to preview a built site with translations.

    For development, prefer the command live (or just mkdocs serve).

    This is here only to preview a site with translations already built.

    Make sure you run the build-all command first.
    """
    typer.echo("Warning: this is a very simple server.")
    typer.echo("For development, use the command live instead.")
    typer.echo("This is here only to preview a site with translations already built.")
    typer.echo("Make sure you run the build-all command first.")
    os.chdir("site")
    server_address = ("", 8008)
    server = HTTPServer(server_address, SimpleHTTPRequestHandler)
    typer.echo("Serving at: http://127.0.0.1:8008")
    server.serve_forever()


@app.command()
def live(
    lang: str = typer.Argument(
        None, callback=lang_callback, autocompletion=complete_existing_lang
    )
) -> None:
    """
    Serve with livereload a docs site for a specific language.

    This only shows the actual translated files, not the placeholders created with
    build-all.

    Takes an optional LANG argument with the name of the language to serve, by default
    en.
    """
    # Enable line numbers during local development to make it easier to highlight
    os.environ["LINENUMS"] = "true"
    if lang is None:
        lang = "en"
    lang_path: Path = docs_path / lang
    os.chdir(lang_path)
    mkdocs.commands.serve.serve(dev_addr="127.0.0.1:8008")


<<<<<<< HEAD
def update_config() -> None:
    config = get_en_config()
    languages = [{"en": "/"}]
    alternate: List[Dict[str, str]] = config["extra"].get("alternate", [])
    alternate_dict = {alt["link"]: alt["name"] for alt in alternate}
    new_alternate: List[Dict[str, str]] = []
=======
def update_config(lang: str):
    lang_path: Path = docs_path / lang
    config_path = lang_path / mkdocs_name
    current_config: dict = mkdocs.utils.yaml_load(
        config_path.read_text(encoding="utf-8")
    )
    if lang == "en":
        config = get_en_config()
    else:
        config = get_base_lang_config(lang)
        config["nav"] = current_config["nav"]
        config["theme"]["language"] = current_config["theme"]["language"]

    languages: List[Dict[str, str]] = []
    alternate: List[Dict[str, str]] = []

    # Language names sourced from https://quickref.me/iso-639-1 . FastAPI
    # contributors may wish to update or change these, e.g. to fix capitalisation.
    local_language_names: Dict[str, str] = json.loads(
        (Path(__file__).parent / "../docs/language_names.json").read_text()
    )
>>>>>>> feat/5060-automatic-language-names
    for lang_path in get_lang_paths():
        if not lang_path.is_dir():
            continue

        code = lang_path.name
        if code == "en":
            # English is served at the root url
            url = "/"
        else:
            # All other languages are served under a path that starts with their
            # language code
            url = f"/{code}/"

        if code in local_language_names:
            # This is for all real languages
            name = f"{code} - {local_language_names[code]}"
        else:
            # This is for test languages, e.g. the language code xx
            name = code

        languages.append({code: url})
        alternate.append({"link": url, "name": name})

    config["nav"][1] = {"Languages": languages}
<<<<<<< HEAD
    config["extra"]["alternate"] = new_alternate
    en_config_path.write_text(
=======
    config["extra"]["alternate"] = alternate
    config_path.write_text(
>>>>>>> feat/5060-automatic-language-names
        yaml.dump(config, sort_keys=False, width=200, allow_unicode=True),
        encoding="utf-8",
    )


@app.command()
def langs_json():
    langs = []
    for lang_path in get_lang_paths():
        if lang_path.is_dir():
            langs.append(lang_path.name)
    print(json.dumps(langs))


if __name__ == "__main__":
    app()
