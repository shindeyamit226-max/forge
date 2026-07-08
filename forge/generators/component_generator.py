"""
Component Generator — generate frontend components, hooks, stores.
Supports: React, Vue, Angular, Svelte.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ComponentSpec:
    name: str
    framework: str
    props: list[dict] = field(default_factory=list)
    state: list[dict] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    methods: list[dict] = field(default_factory=list)
    styles: str = ""


class ComponentGenerator:
    """Generate frontend components."""

    @classmethod
    def generate(cls, spec: ComponentSpec) -> dict[str, str]:
        """Generate component files. Returns {filepath: content}."""
        generators = {
            "react": cls._gen_react,
            "react_ts": cls._gen_react_ts,
            "vue": cls._gen_vue,
            "angular": cls._gen_angular,
            "svelte": cls._gen_svelte,
        }
        gen = generators.get(spec.framework, cls._gen_react_ts)
        return gen(spec)

    @classmethod
    def _gen_react_ts(cls, spec: ComponentSpec) -> dict[str, str]:
        name = spec.name
        files = {}

        # Props interface
        props_type = ""
        if spec.props:
            props_lines = [f"interface {name}Props {{"]
            for p in spec.props:
                optional = "?" if p.get("optional") else ""
                props_lines.append(f"  {p['name']}{optional}: {p.get('type', 'any')}")
            props_lines.append("}")
            props_type = "\n".join(props_lines)

        # State declarations
        state_lines = []
        for s in spec.state:
            state_lines.append(f"  const [{s['name']}, set{s['name'][0].upper()}{s['name'][1:]}] = useState<{s.get('type', 'any')}>({s.get('initial', 'null')})")

        # Component
        component = f"""import React{{ {'useState, ' if spec.state else ''}useEffect }} from 'react'
{f"import './{name}.css'" if spec.styles else ""}

{props_type}

export const {name}: React.FC{f'<{name}Props>' if spec.props else ''} = ({'{' + ', '.join(p['name'] for p in spec.props) + '}' if spec.props else ''}) => {{
{chr(10).join(state_lines)}

  return (
    <div className="{name.lower()}">
      <h2>{name}</h2>
    </div>
  )
}}

export default {name}
"""
        files[f"{name}.tsx"] = component

        # Styles
        if spec.styles:
            files[f"{name}.css"] = f""".{name.lower()} {{
  display: flex;
  flex-direction: column;
  gap: 1rem;
}}
"""

        # Test
        files[f"{name}.test.tsx"] = f"""import {{ render, screen }} from '@testing-library/react'
import {{ {name} }} from './{name}'

describe('{name}', () => {{
  it('renders correctly', () => {{
    render(<{name} />)
    expect(screen.getByText('{name}')).toBeInTheDocument()
  }})
}})
"""

        return files

    @classmethod
    def _gen_react(cls, spec: ComponentSpec) -> dict[str, str]:
        name = spec.name
        return {f"{name}.jsx": f"""import React {{ useState }} from 'react'

export const {name} = (props) => {{
  return (
    <div className="{name.lower()}">
      <h2>{name}</h2>
    </div>
  )
}}

export default {name}
"""}

    @classmethod
    def _gen_vue(cls, spec: ComponentSpec) -> dict[str, str]:
        name = spec.name
        props_script = ""
        if spec.props:
            props_list = ", ".join(f"'{p['name']}'" for p in spec.props)
            props_script = f"  props: [{props_list}],"

        return {f"{name}.vue": f"""<template>
  <div class="{name.lower()}">
    <h2>{name}</h2>
  </div>
</template>

<script setup lang="ts">
{props_script}
</script>

<style scoped>
.{name.lower()} {{
  display: flex;
  flex-direction: column;
}}
</style>
"""}

    @classmethod
    def _gen_angular(cls, spec: ComponentSpec) -> dict[str, str]:
        name = spec.name
        selector = name.lower().replace("component", "")
        return {
            f"{name}.component.ts": f"""import {{ Component }} from '@angular/core'

@Component({{
  selector: 'app-{selector}',
  templateUrl: './{name}.component.html',
  styleUrls: ['./{name}.component.css']
}})
export class {name}Component {{}}
""",
            f"{name}.component.html": f'<div class="{selector}">\n  <h2>{name}</h2>\n</div>\n',
            f"{name}.component.css": f'.{selector} {{ display: flex; flex-direction: column; }}\n',
        }

    @classmethod
    def _gen_svelte(cls, spec: ComponentSpec) -> dict[str, str]:
        name = spec.name
        props_script = ""
        if spec.props:
            props_lines = [f"  export let {p['name']}" for p in spec.props]
            props_script = "\n".join(props_lines)

        return {f"{name}.svelte": f"""<script lang="ts">
{props_script}
</script>

<div class="{name.lower()}">
  <h2>{name}</h2>
</div>

<style>
  .{name.lower()} {{
    display: flex;
    flex-direction: column;
  }}
</style>
"""}
