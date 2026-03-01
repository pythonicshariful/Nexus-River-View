from app import create_app
from models import Director, Customer, Installment, CustomerInstallment, Transaction
from database import db
import unittest

class TestSystem(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_director_shares_and_calculations(self):
        # 1. Create Director
        d = Director(name="Dir 1", total_share=10, per_share_value=1000, land_value_extra_share=500)
        db.session.add(d)
        db.session.commit()
        
        # Verify available shares
        self.assertEqual(d.available_shares, 10)
        
        # 2. Add Customer with shares
        c = Customer(name="Cust 1", customer_id="C1", director_id=d.id, shares=2, total_paid=0, total_price=5000)
        db.session.add(c)
        db.session.commit()
        
        # Verify available shares decreased
        self.assertEqual(d.available_shares, 8)
        
        # 3. Create Installment
        inst = Installment(name="Piling", amount_per_share=100)
        db.session.add(inst)
        db.session.commit()
        
        # Generate CustomerInstallment (manual trigger in test)
        total_amt = c.shares * inst.amount_per_share
        ci = CustomerInstallment(customer_id=c.id, installment_id=inst.id, total_amount=total_amt, due_amount=total_amt)
        db.session.add(ci)
        db.session.commit()
        
        self.assertEqual(ci.total_amount, 200)
        self.assertEqual(ci.due_amount, 200)
        
        # 4. Make Partial Payment
        tx = Transaction(customer_id=c.id, amount=120, date="2024-01-01", customer_installment_id=ci.id)
        ci.paid_amount += tx.amount
        ci.due_amount = ci.total_amount - ci.paid_amount
        c.total_paid += tx.amount
        d.total_paid += tx.amount
        
        db.session.add(tx)
        db.session.commit()
        
        self.assertEqual(ci.due_amount, 80)
        self.assertEqual(c.total_paid, 120)
        # Director total_paid should be 120
        self.assertEqual(d.total_paid, 120)

if __name__ == '__main__':
    unittest.main()
