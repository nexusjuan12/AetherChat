// subscription.js
const stripe = Stripe('your_publishable_key'); // Replace with your Stripe key

class SubscriptionHandler {
    constructor() {
        this.initializeElements();
        this.attachEventListeners();
    }

    initializeElements() {
        // Subscription buttons
        this.upgradeButtons = document.querySelectorAll('.plan-button[data-plan]');
        // Credit purchase buttons
        this.creditButtons = document.querySelectorAll('.plan-button[data-credits]');
    }

    attachEventListeners() {
        // Subscription upgrade listeners
        this.upgradeButtons.forEach(button => {
            button.addEventListener('click', (e) => this.handleUpgrade(e));
        });

        // Credit purchase listeners
        this.creditButtons.forEach(button => {
            button.addEventListener('click', (e) => this.handleCreditPurchase(e));
        });
    }

    async handleUpgrade(event) {
        const button = event.currentTarget;
        button.disabled = true;
        try {
            const plan = button.dataset.plan;
            const price = button.dataset.price;

            // Create subscription checkout session
            const response = await fetch('/api/create-subscription', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    plan: plan,
                    price: price
                })
            });

            const session = await response.json();

            if (session.error) {
                throw new Error(session.error);
            }

            // Redirect to Stripe Checkout
            const result = await stripe.redirectToCheckout({
                sessionId: session.sessionId
            });

            if (result.error) {
                throw new Error(result.error.message);
            }

        } catch (error) {
            console.error('Error:', error);
            this.showError(`Payment failed: ${error.message}`);
            button.disabled = false;
        }
    }

    async handleCreditPurchase(event) {
        const button = event.currentTarget;
        button.disabled = true;
        try {
            const credits = button.dataset.credits;
            const price = button.dataset.price;

            // Create credit purchase payment intent
            const response = await fetch('/api/create-credit-purchase', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    credits: credits,
                    price: price
                })
            });

            const paymentData = await response.json();

            if (paymentData.error) {
                throw new Error(paymentData.error);
            }

            // Handle the payment with Stripe Elements
            const result = await stripe.confirmCardPayment(paymentData.clientSecret, {
                payment_method: {
                    card: this.card,
                    billing_details: {
                        name: paymentData.customerName
                    }
                }
            });

            if (result.error) {
                throw new Error(result.error.message);
            }

            // Payment successful
            if (result.paymentIntent.status === 'succeeded') {
                await this.confirmCreditPurchase(result.paymentIntent.id, credits);
                this.showSuccess(`Successfully purchased ${credits} credits!`);
                // Refresh credit display
                this.updateCreditDisplay();
            }

        } catch (error) {
            console.error('Error:', error);
            this.showError(`Payment failed: ${error.message}`);
            button.disabled = false;
        }
    }

    async confirmCreditPurchase(paymentIntentId, credits) {
        try {
            const response = await fetch('/api/confirm-credit-purchase', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    paymentIntentId: paymentIntentId,
                    credits: credits
                })
            });

            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error);
            }

            return result;
        } catch (error) {
            console.error('Confirmation error:', error);
            throw error;
        }
    }

    async updateCreditDisplay() {
        try {
            const response = await fetch('/api/user-credits');
            const data = await response.json();
            const creditDisplay = document.querySelector('.current-credits h3');
            if (creditDisplay) {
                creditDisplay.textContent = `Credits: ${data.credits}`;
            }
        } catch (error) {
            console.error('Error updating credits:', error);
        }
    }

    showError(message) {
        // Create or update error message element
        let errorDiv = document.getElementById('error-message');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.id = 'error-message';
            errorDiv.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: #ff5555;
                color: white;
                padding: 15px;
                border-radius: 5px;
                z-index: 1000;
                animation: fadeIn 0.3s ease;
            `;
            document.body.appendChild(errorDiv);
        }
        errorDiv.textContent = message;
        setTimeout(() => errorDiv.remove(), 5000);
    }

    showSuccess(message) {
        // Create or update success message element
        let successDiv = document.getElementById('success-message');
        if (!successDiv) {
            successDiv = document.createElement('div');
            successDiv.id = 'success-message';
            successDiv.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: #55ff70;
                color: white;
                padding: 15px;
                border-radius: 5px;
                z-index: 1000;
                animation: fadeIn 0.3s ease;
            `;
            document.body.appendChild(successDiv);
        }
        successDiv.textContent = message;
        setTimeout(() => successDiv.remove(), 5000);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    new SubscriptionHandler();
});

// Add necessary styles
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-20px); }
        to { opacity: 1; transform: translateY(0); }
    }

    .disabled {
        opacity: 0.7;
        cursor: not-allowed;
    }
`;
document.head.appendChild(style);
