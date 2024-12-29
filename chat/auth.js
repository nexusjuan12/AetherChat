// Auth state management
let currentUser = null;

// DOM Elements
const authModal = document.getElementById('auth-modal');
const loginForm = document.getElementById('login-form');
const registerForm = document.getElementById('register-form');
const logoutButton = document.getElementById('logout-button');
const loginError = document.getElementById('login-error');
const registerError = document.getElementById('register-error');

// Check authentication status
async function checkAuth() {
    try {
        const response = await fetch('/auth/user', {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            currentUser = data.user;
            updateAuthUI();
            return true;
        }
        currentUser = null;
        updateAuthUI();
        return false;
    } catch (error) {
        console.error('Auth check failed:', error);
        currentUser = null;
        updateAuthUI();
        return false;
    }
}

// Update UI based on auth state
function updateAuthUI() {
    const loggedOutView = document.getElementById('logged-out-view');
    const loggedInView = document.getElementById('logged-in-view');
    const usernameDisplay = document.getElementById('username-display');
    const creditsDisplay = document.getElementById('credits-display');
    
    if (!loggedOutView || !loggedInView) return;

    if (currentUser) {
        loggedOutView.style.display = 'none';
        loggedInView.style.display = 'block';
        if (usernameDisplay) usernameDisplay.textContent = currentUser.username;
        if (creditsDisplay) creditsDisplay.textContent = `Credits: ${currentUser.credits}`;
        
        // Enable create character button if it exists
        const createCharacterBtn = document.getElementById('create-character');
        if (createCharacterBtn) createCharacterBtn.disabled = false;
    } else {
        loggedOutView.style.display = 'block';
        loggedInView.style.display = 'none';
        
        // Disable create character button if it exists
        const createCharacterBtn = document.getElementById('create-character');
        if (createCharacterBtn) createCharacterBtn.disabled = true;
    }
}

// Modal controls
function openAuthModal(type = 'login') {
    if (!authModal) return;
    authModal.showModal();
    switchAuthForm(type);
}

function closeAuthModal() {
    if (!authModal) return;
    authModal.close();
    loginForm?.reset();
    registerForm?.reset();
    if (loginError) loginError.textContent = '';
    if (registerError) registerError.textContent = '';
}

function switchAuthForm(type) {
    if (!loginForm || !registerForm) return;
    loginForm.style.display = type === 'login' ? 'block' : 'none';
    registerForm.style.display = type === 'register' ? 'block' : 'none';
}

// Handle login
async function handleLogin(e) {
    e.preventDefault();
    if (!loginError) return;
    loginError.textContent = '';
    
    const username = document.getElementById('login-username')?.value;
    const password = document.getElementById('login-password')?.value;
    
    try {
        const response = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentUser = data.user;
            updateAuthUI();
            closeAuthModal();
            // Reload characters if the function exists
            if (typeof loadCharacters === 'function') {
                await loadCharacters();
            }
        } else {
            loginError.textContent = data.error || 'Login failed';
        }
    } catch (error) {
        console.error('Login error:', error);
        loginError.textContent = 'Login failed. Please try again.';
    }
}

// Handle registration
async function handleRegister(e) {
    e.preventDefault();
    if (!registerError) return;
    registerError.textContent = '';
    
    const username = document.getElementById('register-username')?.value;
    const password = document.getElementById('register-password')?.value;
    
    try {
        const response = await fetch('/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentUser = data.user;
            updateAuthUI();
            closeAuthModal();
            // Reload characters if the function exists
            if (typeof loadCharacters === 'function') {
                await loadCharacters();
            }
        } else {
            registerError.textContent = data.error || 'Registration failed';
        }
    } catch (error) {
        console.error('Registration error:', error);
        registerError.textContent = 'Registration failed. Please try again.';
    }
}

// Handle logout
async function handleLogout() {
    try {
        const response = await fetch('/auth/logout', {
            credentials: 'include'
        });
        
        if (response.ok) {
            currentUser = null;
            updateAuthUI();
            // Reload characters if the function exists
            if (typeof loadCharacters === 'function') {
                await loadCharacters();
            }
            // Redirect to home page if we're on a protected page
            if (window.location.pathname !== '/' && window.location.pathname !== '/index.html') {
                window.location.href = '/';
            }
        }
    } catch (error) {
        console.error('Logout error:', error);
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    
    logoutButton?.addEventListener('click', handleLogout);
    document.getElementById('close-auth-modal')?.addEventListener('click', closeAuthModal);
    
    loginForm?.addEventListener('submit', handleLogin);
    registerForm?.addEventListener('submit', handleRegister);
    
    document.querySelector('.switch-to-register')?.addEventListener('click', () => switchAuthForm('register'));
    document.querySelector('.switch-to-login')?.addEventListener('click', () => switchAuthForm('login'));
});

export {
    currentUser,
    checkAuth,
    updateAuthUI,
    openAuthModal
};