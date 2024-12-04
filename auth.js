import { loadCharacters } from './script.js';

// Auth state management
let currentUser = null;

// DOM Elements
const authModal = document.getElementById('auth-modal');
const loginButton = document.getElementById('login-button');
const registerButton = document.getElementById('register-button');
const logoutButton = document.getElementById('logout-button');
const switchToRegisterButton = document.querySelector('.switch-to-register');
const switchToLoginButton = document.querySelector('.switch-to-login');
const loginError = document.getElementById('login-error');
const registerError = document.getElementById('register-error');
const closeAuthModalButton = document.getElementById('close-auth-modal');

// Check authentication status
async function checkAuth() {
    try {
        const response = await fetch('/auth/user', {
            credentials: 'include',
            headers: {
                'Cache-Control': 'no-cache'
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            currentUser = data.user;
            updateAuthUI();
            return true;
        } else {
            currentUser = null;
            updateAuthUI();
            return false;
        }
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
    const createCharacterBtn = document.getElementById('create-character');

    if (currentUser) {
        loggedOutView.style.display = 'none';
        loggedInView.style.display = 'block';
        usernameDisplay.textContent = currentUser.username;
        creditsDisplay.textContent = `Credits: ${currentUser.credits}`;
        createCharacterBtn.disabled = false;
    } else {
        loggedOutView.style.display = 'block';
        loggedInView.style.display = 'none';
        createCharacterBtn.disabled = true;
    }
}

// Modal controls
function openAuthModal(type = 'login') {
    authModal.showModal();
    switchAuthForm(type);
}

function closeAuthModal() {
    authModal.close();
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    loginForm?.reset();
    registerForm?.reset();
    if (loginError) loginError.textContent = '';
    if (registerError) registerError.textContent = '';
}

function switchAuthForm(type) {
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    if (!loginForm || !registerForm) return;

    if (type === 'login') {
        loginForm.style.display = 'block';
        registerForm.style.display = 'none';
    } else {
        loginForm.style.display = 'none';
        registerForm.style.display = 'block';
    }
}

// Handle login
async function handleLogin(e) {
    e.preventDefault();
    if (!loginError) return;
    loginError.textContent = '';
    
    const email = document.getElementById('login-email')?.value;
    const password = document.getElementById('login-password')?.value;
    
    try {
        const response = await fetch('/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ email, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentUser = data.user;
            updateAuthUI();
            closeAuthModal();
            await loadCharacters();
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
    const email = document.getElementById('register-email')?.value;
    const password = document.getElementById('register-password')?.value;
    
    try {
        const response = await fetch('/auth/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ username, email, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentUser = data.user;
            updateAuthUI();
            closeAuthModal();
            await loadCharacters();
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
            await loadCharacters();
        }
    } catch (error) {
        console.error('Logout error:', error);
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    
    loginButton?.addEventListener('click', () => openAuthModal('login'));
    registerButton?.addEventListener('click', () => openAuthModal('register'));
    logoutButton?.addEventListener('click', handleLogout);
    closeAuthModalButton?.addEventListener('click', closeAuthModal);
    
    document.getElementById('login-form')?.addEventListener('submit', handleLogin);
    document.getElementById('register-form')?.addEventListener('submit', handleRegister);
    
    document.querySelector('.switch-to-register')?.addEventListener('click', () => switchAuthForm('register'));
    document.querySelector('.switch-to-login')?.addEventListener('click', () => switchAuthForm('login'));
});

export {
    currentUser,
    checkAuth,
    updateAuthUI,
    openAuthModal
};