"""Go language plugin — golangci-lint + go vet + tree-sitter.

Originally contributed by tinker495 (KyuSeok Jung) in PR #128.
Adapted to the generic_lang framework with tree-sitter integration.
"""

from desloppify.engine.policy.zones import COMMON_ZONE_RULES, Zone, ZoneRule
from desloppify.languages._framework.generic import generic_lang
from desloppify.languages._framework.treesitter._specs import GO_SPEC

from . import test_coverage as _go_test_coverage

GO_ZONE_RULES = [ZoneRule(Zone.TEST, ["_test.go"])] + COMMON_ZONE_RULES

generic_lang(
    name="go",
    extensions=[".go"],
    tools=[
        {
            "label": "golangci-lint",
            "cmd": "golangci-lint run --out-format=json",
            "fmt": "golangci",
            "id": "golangci_lint",
            "tier": 2,
            "fix_cmd": "golangci-lint run --fix",
        },
        {
            "label": "go vet",
            "cmd": "go vet ./...",
            "fmt": "gnu",
            "id": "vet_error",
            "tier": 3,
            "fix_cmd": None,
        },
    ],
    exclude=["vendor", "testdata"],
    depth="standard",
    detect_markers=["go.mod"],
    treesitter_spec=GO_SPEC,
    zone_rules=GO_ZONE_RULES,
    test_coverage_module=_go_test_coverage,
)
