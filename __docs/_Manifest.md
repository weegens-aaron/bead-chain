# FlowDoc Manifest — bead-chain (maintainer)

Inventory of every doc to write, grouped and banded by type. Each doc bead, when
it finishes its item, ticks the box `[x]` and bumps the counters below.

> [!NOTE]
> bead-chain is a terminal Code Puppy plugin with **no HTTP endpoints and no web
> views**. The Endpoints (050+) and Views (060/070+) bands are therefore
> intentionally empty — only Features, Flows, and Concepts are documented.

## Progress

- **Total:** 22
- **Done:** 21
- **Remaining:** 1

---

## Features (001+)

- [ ] 001 | Feature: BeadChaining -> [BeadChaining](Features/BeadChaining.md)
- [x] 002 | Feature: RecoveryMode -> [RecoveryMode](Features/RecoveryMode.md)
- [x] 003 | Feature: WorkTimeBlockerGate -> [WorkTimeBlockerGate](Features/WorkTimeBlockerGate.md)
- [x] 004 | Feature: EpicAffinity -> [EpicAffinity](Features/EpicAffinity.md)
- [x] 005 | Feature: BlockingBugPriority -> [BlockingBugPriority](Features/BlockingBugPriority.md)
- [x] 006 | Feature: CloseGuard -> [CloseGuard](Features/CloseGuard.md)
- [x] 007 | Feature: EpicRollup -> [EpicRollup](Features/EpicRollup.md)
- [x] 008 | Feature: BugDiscoveryProtocol -> [BugDiscoveryProtocol](Features/BugDiscoveryProtocol.md)
- [x] 009 | Feature: GoalPromptEnrichment -> [GoalPromptEnrichment](Features/GoalPromptEnrichment.md)

## Flows (010+)

- [x] 010 | Flow: ChainIterationLoop -> [ChainIterationLoop](Flows/ChainIterationLoop.md)
- [x] 011 | Flow: NextBeadSelectionWaterfall -> [NextBeadSelectionWaterfall](Flows/NextBeadSelectionWaterfall.md)
- [x] 012 | Flow: BeadClaimAndBlockerRecheck -> [BeadClaimAndBlockerRecheck](Flows/BeadClaimAndBlockerRecheck.md)
- [x] 013 | Flow: StrandedBeadRecovery -> [StrandedBeadRecovery](Flows/StrandedBeadRecovery.md)
- [x] 014 | Flow: SessionEndEpicRollup -> [SessionEndEpicRollup](Flows/SessionEndEpicRollup.md)
- [x] 015 | Flow: GoalPromptConstruction -> [GoalPromptConstruction](Flows/GoalPromptConstruction.md)

## Endpoints (050+)

_None — bead-chain exposes no HTTP API._

## Views (060/070+)

_None — bead-chain has no web views/pages._

## Concepts (080+)

- [x] 080 | Concept: QueueDriverNotGoalEngine -> [QueueDriverNotGoalEngine](Concepts/QueueDriverNotGoalEngine.md)
- [x] 081 | Concept: ContainerTypeExclusion -> [ContainerTypeExclusion](Concepts/ContainerTypeExclusion.md)
- [x] 082 | Concept: SessionCloseDurability -> [SessionCloseDurability](Concepts/SessionCloseDurability.md)
- [x] 083 | Concept: BdSubprocessTransport -> [BdSubprocessTransport](Concepts/BdSubprocessTransport.md)
- [x] 084 | Concept: ChainStateSingleton -> [ChainStateSingleton](Concepts/ChainStateSingleton.md)
- [x] 085 | Concept: ExecutionHints -> [ExecutionHints](Concepts/ExecutionHints.md)
- [x] 086 | Concept: RecurringMoleculeProtection -> [RecurringMoleculeProtection](Concepts/RecurringMoleculeProtection.md)
