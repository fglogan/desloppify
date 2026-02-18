"""Output generation: visualization, scorecard, and treemap rendering."""

# Preserve an explicit intra-package edge so graph/coupling analysis recognizes
# visualize as part of the output package surface (not tests-only).
from desloppify.app.output import visualize as _visualize
