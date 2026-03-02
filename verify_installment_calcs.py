import os
import sys

# Add working directory to path for imports
sys.path.append(os.getcwd())

from app import create_app
from models import db, Installment, CustomerInstallment, Customer, Director

app = create_app()

def verify_calculations():
    with app.app_context():
        print("--- Verifying Installment Aggregate Calculations ---")
        
        # Check if there are any installments
        installments = Installment.query.all()
        if not installments:
            print("No installments found to verify. Please create one manually in the app.")
            return

        for inst in installments:
            print(f"\nInstallment: {inst.name} (Amount/Share: {inst.amount_per_share})")
            
            # Manual calculation
            total_expected = 0
            total_paid = 0
            total_due = 0
            
            for ci in inst.customer_installments:
                total_expected += ci.total_amount
                total_paid += ci.paid_amount
                total_due += ci.due_amount
            
            print(f"Calculated - Expected: {total_expected}, Collected: {total_paid}, Due: {total_due}")
            print(f"Model Property - Expected: {inst.total_expected}, Collected: {inst.total_collected}, Due: {inst.total_due}")
            
            assert abs(total_expected - inst.total_expected) < 0.01
            assert abs(total_paid - inst.total_collected) < 0.01
            assert abs(total_due - inst.total_due) < 0.01
            
            print("SUCCESS: Calculations match.")

if __name__ == "__main__":
    verify_calculations()
