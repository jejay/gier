class BankAccount:
    def __init__(self, owner, balance=0):
        self.owner = owner
        self.balance = balance
        self.history = []

    def deposit(self, amount):
        if amount <= 0:
            return False
        self.balance += amount
        self.history.append(("deposit", amount))
        return True

    def withdraw(self, amount):
        if amount <= 0 or amount > self.balance:
            return False
        self.balance -= amount
        self.history.append(("withdraw", amount))
        return True

    def statement(self):
        lines = []
        lines.append(f"Account of {self.owner}")
        for kind, amount in self.history:
            if kind == "deposit":
                lines.append(f"  +{amount}")
            else:
                lines.append(f"  -{amount}")
        lines.append(f"Balance: {self.balance}")
        return "\n".join(lines)
