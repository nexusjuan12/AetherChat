// creditStatus.js
export class CreditStatus {
    constructor(container) {
        this.container = container;
        this.setup();
    }

    setup() {
        this.statusBar = document.createElement('div');
        this.statusBar.className = 'credit-status';
        this.statusBar.innerHTML = `
            <div class="credit-balance">
                <span class="credit-amount"></span> credits
            </div>
            <div class="credit-warning hidden">
                <button class="get-credits-btn">Get More Credits</button>
            </div>
        `;
        this.container.appendChild(this.statusBar);
        this.updateCredits();
    }

    updateCredits(amount) {
        fetch('/auth/user')
            .then(res => res.json())
            .then(data => {
                const credits = data.user.credits;
                this.statusBar.querySelector('.credit-amount').textContent = credits;
                
                // Show warning if credits are low
                if (credits < 100) {
                    this.showWarning();
                }
            });
    }

    showWarning() {
        const warning = this.statusBar.querySelector('.credit-warning');
        warning.classList.remove('hidden');
    }
}
