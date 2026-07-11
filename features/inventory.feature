Feature: zkm-inventory — searchable asset inventory from a hand-authored manifest
  As someone tracking external drives and hardware
  I want a manifest rendered into searchable markdown
  So that `zkm search` can tell me where an asset is and what state it's in

  Background:
    Given a zkm store
    And an inventory manifest with `drives:` and `devices:` lists

  Scenario: Drives lane renders one document per drive
    When I run `zkm convert inventory`
    Then one `inventory/drives/<id>.md` is written per drive
    And each carries `source: inventory` and a typed `scope:inventory.drive` entity
    And the rendered body contains the drive's purpose and data classes

  Scenario: Devices lane renders one document per hardware device
    When I run `zkm convert inventory`
    Then one `inventory/devices/<id>.md` is written per device
    And each carries a typed `scope:inventory.device` entity and its status

  Scenario: A dust-collecting device is findable by status
    Given a device with status "dust-collecting"
    When I run `zkm convert inventory` and `zkm index`
    Then `zkm search dust-collecting` surfaces that device's document

  Scenario: Re-running an unchanged manifest is a no-op
    When I run `zkm convert inventory` twice
    Then the second run creates no new documents and changes no bytes

  @manual
  Scenario: CLI surface — convert dispatches to the inventory plugin
    When I run `zkm convert inventory` at the shell
    Then the store gains `inventory/drives/` and `inventory/devices/` documents
    And the convert is auto-committed scoped to the `inventory/` dir only

  @future @lane-c
  Scenario: Find-dump drive-content index locates a file across drives (ROADMAP id:46b6)
    Given the find-dump lane has swept each drive's file listing
    When I run `zkm search "<a movie title>"`
    Then the result names which drive holds it
    # git-annex independent — covers bulk non-annex content; fast-follow after v1.
