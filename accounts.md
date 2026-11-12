# BUILD Admin Console: Accounts & Sign-in

Each member has their own account, which is their school email plus a password. There is no sign-up page: an admin creates accounts with the steps below. The app never sends email; your email is only your login name.

---

## For everyone: signing in

1. **Get `.env.local` from an admin**, privately (a DM, not a group chat). Put it in the project's root folder.
   - Never commit it or paste it anywhere. It contains the database's admin password.
2. **Start the app** from the project folder:
   ```bash
   npm install
   npm run dev
   ```
3. **Open http://localhost:3000** and sign in with your school email and the password an admin sent you.
4. **Save your password in a password manager**, then delete the DM it came in.

**"Wrong email or password"?** Check for typos in your email. If it still fails, ask an admin to check your account (see *Troubleshooting*).

---

## For admins: creating an account

Run all commands from the project folder (after `npm install`).

**1. Generate a random password and its hash**

```bash
node -e "const p=require('crypto').randomBytes(9).toString('base64url');console.log('Password:',p);console.log('Hash:',require('bcryptjs').hashSync(p,10))"
```

This prints a random 12-character **Password** and its **Hash** (starts with `$2b$10$`).

**2. Add the person in Supabase**: Dashboard → **SQL Editor** → **New query**:

```sql
insert into users (email, name, role, password_hash)
values ('NETID@umass.edu', 'FULL NAME', 'member', 'PASTE_HASH')
on conflict (email) do update
  set password_hash = excluded.password_hash, role = excluded.role;
```

- Write the email in **lowercase**.
- `on conflict` means this also works if the person already has an account (it updates their password and role).
- Delete the saved query afterwards so the hash isn't left in the editor.

**3. Send the password to that person only** in a private DM. Then clear your terminal (⌘K on Mac) so the password isn't left on screen.

### Roles

| Role | Can do |
|---|---|
| `member` | View the console |
| `reviewer` | View, plus approve/reject sites |
| `admin` | Everything, including managing accounts |

---

## For admins: other account tasks

**Reset a forgotten password**: repeat *Creating an account* steps 1–3 with the same email. The old password stops working.

**Change someone's role**
```sql
update users set role = 'reviewer' where email = 'NETID@umass.edu';
```

**Remove someone's access**
```sql
update users set password_hash = null where email = 'NETID@umass.edu';
```
- This blocks their sign-in but keeps their history (approvals they made stay linked to them). Don't delete the row.
- They may stay signed in for up to 30 days on a browser where they're already logged in. To sign everyone out immediately, the lead changes `AUTH_SECRET` in `.env.local` and shares the new file.
- **If they had `.env.local`, the lead should also change the database password** in Supabase and share the updated file with everyone else.

---

## Troubleshooting

**Check an account** (shows the role and whether a password is set, never the password itself):
```sql
select email, role, password_hash is not null as has_password
from users
where email = 'NETID@umass.edu';
```

| Problem | Fix |
|---|---|
| No row found | The account was never created. Follow *Creating an account* |
| `has_password` is `false` | Access was removed, or the password was never set. Reset it |
| Email has capital letters | Re-run the insert with the email in lowercase |
| `Cannot find module 'bcryptjs'` | Run `npm install` first, from the project folder |

---

## Security rules

- **Passwords are never stored.** The database only keeps the hash, which can't be turned back into the password. Nobody (admins included) can look up your password.
- **Always use the generated random passwords.** Never use a pattern like `NamePassword123`: if one person knows the pattern, they can guess everyone's.
- **`.env.local` is a master key.** Anyone with it has full access to the database, including all nonprofit intake data. Share it only privately, and only with current members.
