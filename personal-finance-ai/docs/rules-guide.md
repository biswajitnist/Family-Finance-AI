# Rules: Automatic Transaction Classification

## What rules are for

Rules teach Ledger Local how you want familiar transactions classified.

When a statement is processed, Ledger Local checks active rules before asking
the local AI classifier. A matching rule can set a category such as Grocery or
Subscriptions, or correct whether a transaction is income or an expense.

Rules are useful for merchants and payment descriptions that appear regularly.
They reduce repeated manual corrections during statement review.

## Simple example

To classify REWE purchases as groceries:

1. Open **Rules**.
2. Enter `REWE groceries` as the rule name.
3. Choose **Merchant name contains**.
4. Enter `REWE` as the text to find.
5. Choose **Set category**.
6. Select `Grocery` from the existing category list.
7. Select **Add rules**.

New matching statement rows will receive the Grocery category automatically.

## The fields in plain English

### Rule name

A short name that helps you remember the purpose of the rule. It does not
affect matching.

Example: `Netflix subscription`.

### What should be matched?

- **Merchant name contains** checks the displayed merchant or vendor name.
- **Description contains** checks both the merchant and the longer transaction
  description. Use this when the merchant name changes but a reliable word
  appears in the payment reference.

Matching ignores uppercase and lowercase differences. For example, `rewe`
matches `REWE`.

### Text to find

The merchant name or reliable word that identifies the transaction.

Good examples include `REWE`, `Netflix`, `Employer`, and `Stadt Wolfsburg`.
Use a specific phrase when a short word could match unrelated transactions.

### What should happen?

- **Set category** assigns one of the categories already created in Ledger
  Local, such as Grocery, Rent, Salary, Education, or Subscriptions.
- **Set income or expense type** changes the transaction direction. Enter
  `credit` for money received or `debit` for money paid.

### Category or type

For a category rule, select a category from the list. The dropdown uses the
categories already saved on the Categories page, which prevents spelling
mistakes and accidental duplicate names.

For a transaction-type rule, enter `credit` or `debit`.

## Applying rules

Rules run automatically on newly extracted statement rows.

Select **Apply all rules** to apply saved rules to existing transactions that
are still waiting for review. Validated transactions are not changed.

After applying rules, review the affected rows before confirming the import.

## More examples

- Merchant contains `Netflix` -> category `Subscriptions`
- Merchant contains `REWE` -> category `Grocery`
- Description contains `Gehalt` -> category `Salary`
- Description contains `Essengeld` -> category `Education`
- Description contains `salary` -> transaction type `credit`

## If a rule does not work

Check the following:

1. The text appears in the extracted merchant or description.
2. The category already exists and its spelling matches.
3. The transaction is still waiting for review.
4. The rule is saved.

Use a broader but still distinctive phrase if the statement changes the
merchant wording between months.

Rules and their transaction data remain on this machine. They do not require a
cloud AI service.
