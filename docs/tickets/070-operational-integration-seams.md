# Ticket 070: Operational Integration Seams

## Goal

Define integration boundaries without turning the simulator into an operational control system.

## Current Gap

There are no explicit seams for live comms state, UTM/U-space, Remote ID,
traffic observations, operational intent, conformance checks, or evidence
governance.

## Scope

- Add UTM/U-space seam interfaces.
- Add live comms-state seam interfaces.
- Add Remote ID and traffic-observation seam interfaces.
- Add operational intent export/import shape.
- Add conformance-check abstraction.
- Add migration docs.
- Add evidence standards.
- Add stronger governance docs for schema and output evolution.

## Acceptance Criteria

- The platform can integrate with operational workflows while keeping core simulation deterministic and testable.

## Out of Scope

- Claiming operational approval.
- Replacing operator tooling or regulator workflows.
- Live network adapters. Those belong in Ticket 071 after the seams are defined.
