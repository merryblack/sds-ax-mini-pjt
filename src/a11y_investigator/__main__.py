"""`python -m a11y_investigator ...` runs the same CLI as `a11y-investigator ...`."""
from a11y_investigator.cli import app

app(prog_name="a11y-investigator")
