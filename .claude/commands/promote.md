---
description: "Promote patches through the gcp-hcp-apps fleet"
argument-hint: "<cluster-type> <component> <patch-name>"
allowed-tools: ["Bash"]
---

# Promote Fleet Patches

Promotes patches through the gcp-hcp-apps fleet management system using the promote.py script.

This command requires exactly 3 arguments. If any are missing, show available options using `tree config/<cluster-type>/<component>` to help the user see existing patches.

To list all ongoing patches across the fleet for each cluster-type and application, use:
`find config -name "patch-*.yaml" | awk -F'/' '{print $2 "\t" $3 "\t" $NF}' | sed 's/\.yaml$//' | sort -u`

Arguments provided:
- cluster-type: $1
- component: $2
- patch-name: $3

If parameters are missing or incomplete, use the Bash tool to show available options before asking for the missing parameters.

---

Promoting patch $3 for component $2 in cluster-type $1...

!uv run hack/promote.py $1 $2 $3

Running fleet generation...

!make generate

**Summary of changes:**

!git status --porcelain config/ rendered/

**✅ Promotion complete!**

**Next steps:**
1. Review the changes above
2. Run: `git add config/ rendered/`
3. Run: `git commit -m "Promote $3 for $2"`
4. Run: `git push`
