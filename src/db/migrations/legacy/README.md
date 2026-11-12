# Archived migration drafts

These files were present in the repository but were never registered in
`../meta/_journal.json`. They do not form a migration chain and must not be run:

- `0000_foamy_makkari.sql` independently creates auth tables and a duplicate
  `users` table and `user_role` enum.
- `0001_classy_diamondback.sql` only adds a password column; its snapshot descends
  from an unrelated, missing snapshot and omits the application's other tables.
- `0001_intake_submissions.sql` describes a different, incompatible intake schema.

They are retained here for history. The registered migrations in the parent
directory are the supported migration path from an empty database or a database
that has applied `0000_mixed_absorbing_man`.

If any of these drafts were applied manually, inspect and reconcile that database
against `src/db/schema` before migrating. The supported migrations never drop or
reset existing tables.
