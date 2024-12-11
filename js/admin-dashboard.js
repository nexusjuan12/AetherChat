// Global variables for modals
let currentCharacterId = null;
let currentUserId = null;
let rejectModal = null;
let creditsModal = null;

// Initialize when document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap modals
    rejectModal = new bootstrap.Modal(document.getElementById('rejectModal'));
    creditsModal = new bootstrap.Modal(document.getElementById('creditsModal'));

    // Set up event listeners
    document.getElementById('confirmReject').addEventListener('click', handleReject);
    document.getElementById('confirmCredits').addEventListener('click', handleCreditsUpdate);

    // Load initial data
    loadStats();
    loadPendingCharacters();
    loadUsers();

    // Set up periodic refresh
    setInterval(() => {
        loadStats();
        loadPendingCharacters();
        loadUsers();
    }, 30000); // Refresh every 30 seconds
});

// Load dashboard statistics
async function loadStats() {
    try {
        const response = await fetch('/api/admin/stats');
        const stats = await response.json();
        
        document.getElementById('pendingCount').textContent = stats.pending_characters;
        document.getElementById('approvedCount').textContent = stats.approved_characters;
        document.getElementById('rejectedCount').textContent = stats.rejected_characters;
        document.getElementById('totalCount').textContent = stats.total_characters;
        document.getElementById('totalUsers').textContent = stats.total_users;
        document.getElementById('totalTransactions').textContent = stats.total_transactions;
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Load pending characters
async function loadPendingCharacters() {
    try {
        const response = await fetch('/admin/characters/pending');
        const characters = await response.json();
        console.log('Pending characters:', characters); // Debug log
        
        const container = document.getElementById('pendingCharacters');
        container.innerHTML = characters.map(char => {
            console.log('Processing character:', char); // Debug log
            console.log('Background path:', char.background); // Debug log
            
            return `
                <div class="col-md-6 mb-4">
                    <div class="card">
                        <div class="card-body">
                            <h5 class="card-title">${char.name}</h5>
                            <p class="card-text">${char.description}</p>
                            
                            <div class="avatar-preview mb-3">
                                <h5>Avatar:</h5>
                                <img src="${char.avatar}" class="img-fluid" alt="Avatar">
                            </div>
                            
                            <div class="background-preview mb-3">
                                <h5>Background:</h5>
                                ${char.background ? 
                                    (char.background.toLowerCase().endsWith('.mp4') || 
                                     char.background.toLowerCase().endsWith('.webm') || 
                                     char.background.toLowerCase().endsWith('.wmv') ?
                                        `<video controls class="background-preview-media">
                                            <source src="${char.background}" type="video/mp4">
                                            Your browser does not support the video tag.
                                        </video>` :
                                        `<img src="${char.background}" class="background-preview-media" alt="Background">`)
                                    : '<p>No background uploaded</p>'
                                }
                            </div>
                            
                            <div class="d-flex justify-content-between">
                                <button class="btn btn-success" onclick="approveCharacter('${char.id}')">
                                    Approve
                                </button>
                                <button class="btn btn-danger" onclick="showRejectionModal('${char.id}')">
                                    Reject
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading pending characters:', error);
    }
}

// Load users
async function loadUsers() {
    try {
        const response = await fetch('/api/admin/users');
        const users = await response.json();
        const userList = document.getElementById('userList');
        
        userList.innerHTML = users.map(user => `
            <div class="user-card">
                <div class="row align-items-center">
                    <div class="col-md-4">
                        <h6 class="mb-0"><strong>Username:</strong> ${user.username}</h6>
                        <p class="mb-0"><small><strong>Email:</strong> ${user.email}</small></p>
                    </div>
                    <div class="col-md-3">
                        <p class="mb-0"><strong>Credits:</strong> ${user.credits}</p>
                        <p class="mb-0"><strong>Status:</strong> 
                            <span class="badge ${user.is_active ? 'bg-success' : 'bg-danger'}">
                                ${user.is_active ? 'Active' : 'Inactive'}
                            </span>
                        </p>
                    </div>
                    <div class="col-md-5">
                        <div class="user-actions">
                            ${user.is_active ? 
                                `<button class="btn btn-warning btn-sm" onclick="toggleUserStatus('${user.id}', false)">Suspend</button>` :
                                `<button class="btn btn-success btn-sm" onclick="toggleUserStatus('${user.id}', true)">Activate</button>`
                            }
                            <button class="btn btn-primary btn-sm" onclick="showCreditsModal('${user.id}')">Modify Credits</button>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading users:', error);
    }
}

// Character management functions
async function approveCharacter(characterId) {
    try {
        const response = await fetch(`/admin/characters/${characterId}/approve`, {
            method: 'POST'
        });
        if (response.ok) {
            loadStats();
            loadPendingCharacters();
        }
    } catch (error) {
        console.error('Error approving character:', error);
    }
}

function showRejectModal(characterId) {
    currentCharacterId = characterId;
    document.getElementById('rejectionReason').value = '';
    rejectModal.show();
}

async function handleReject() {
    const reason = document.getElementById('rejectionReason').value;
    if (reason && currentCharacterId) {
        try {
            const response = await fetch(`/admin/characters/${currentCharacterId}/reject`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ reason })
            });
            if (response.ok) {
                rejectModal.hide();
                loadStats();
                loadPendingCharacters();
            }
        } catch (error) {
            console.error('Error rejecting character:', error);
        }
    }
}

async function clearStatus(characterId) {
    try {
        const response = await fetch(`/admin/characters/${characterId}/clear`, {
            method: 'POST'
        });
        if (response.ok) {
            loadStats();
            loadPendingCharacters();
        }
    } catch (error) {
        console.error('Error clearing character status:', error);
    }
}

// User management functions
async function toggleUserStatus(userId, newStatus) {
    try {
        const response = await fetch(`/api/admin/users/${userId}/toggle-status`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: newStatus })
        });
        if (response.ok) {
            loadUsers();
        }
    } catch (error) {
        console.error('Error toggling user status:', error);
    }
}

function showCreditsModal(userId) {
    currentUserId = userId;
    document.getElementById('creditsAmount').value = '';
    creditsModal.show();
}

async function handleCreditsUpdate() {
    const amount = document.getElementById('creditsAmount').value;
    if (amount && currentUserId) {
        try {
            const response = await fetch(`/api/admin/users/${currentUserId}/credits`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ amount: parseInt(amount) })
            });
            if (response.ok) {
                creditsModal.hide();
                loadUsers();
            }
        } catch (error) {
            console.error('Error updating user credits:', error);
        }
    }
}
