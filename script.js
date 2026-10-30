document.addEventListener('DOMContentLoaded', () => {
    // Selection mechanism for sidebar items
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.content-section');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Remove active state from all nav buttons
            navItems.forEach(nav => nav.classList.remove('active'));
            // Add active state to clicked element
            item.classList.add('active');

            // Hide all sections
            sections.forEach(sec => sec.classList.remove('active'));
            
            // Show the targeted section
            const targetId = item.getAttribute('data-target');
            const targetSection = document.getElementById(targetId);
            if(targetSection) {
                targetSection.classList.add('active');
            }
        });
    });

    // Live Search & Filtering
    const searchInput = document.querySelector('.header-search input');
    const filterChips = document.querySelectorAll('.filter-chip');

    // Only filter event cards inside the #events-grid (New Events section)
    const eventsGrid = document.getElementById('events-grid');

    let searchDebounceTimer = null;

    const filterItems = () => {
        const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
        const activeChip = document.querySelector('.filter-chip.active');
        const activeCategory = activeChip ? activeChip.getAttribute('data-filter') : 'All';

        // If user is typing, auto-switch to the New Events section
        if (query.length > 0) {
            const newEventsSection = document.getElementById('new-events');
            const allSections = document.querySelectorAll('.content-section');
            const allNavItems = document.querySelectorAll('.nav-item');
            allSections.forEach(s => s.classList.remove('active'));
            allNavItems.forEach(n => n.classList.remove('active'));
            if (newEventsSection) newEventsSection.classList.add('active');
            const newEventsNavBtn = document.querySelector('[data-target="new-events"]');
            if (newEventsNavBtn) newEventsNavBtn.classList.add('active');
        }

        // Filter only cards in the main events grid
        if (!eventsGrid) return;
        const cards = eventsGrid.querySelectorAll('.event-card');
        let visibleCount = 0;

        cards.forEach(card => {
            const titleEl = card.querySelector('h3');
            const hostEl = card.querySelector('.card-meta span:first-child');
            const descEl = card.querySelector('.card-desc');

            const title = titleEl ? titleEl.textContent.toLowerCase() : '';
            const host = hostEl ? hostEl.textContent.toLowerCase() : '';
            const desc = descEl ? descEl.textContent.toLowerCase() : '';
            const category = card.getAttribute('data-category') || '';

            const matchesText = !query ||
                title.includes(query) ||
                host.includes(query) ||
                desc.includes(query) ||
                category.toLowerCase().includes(query);

            const matchesChip = activeCategory === 'All' ||
                category.toLowerCase() === activeCategory.toLowerCase();

            if (matchesText && matchesChip) {
                card.style.display = '';
                visibleCount++;
            } else {
                card.style.display = 'none';
            }
        });

        // Show/hide "no results" message
        let noResultsEl = eventsGrid.querySelector('.no-results-msg');
        if (visibleCount === 0) {
            if (!noResultsEl) {
                noResultsEl = document.createElement('div');
                noResultsEl.className = 'no-results-msg';
                noResultsEl.style.cssText = 'grid-column:1/-1;padding:3rem;text-align:center;color:var(--text-secondary);';
                noResultsEl.innerHTML = `<i class="fa-solid fa-magnifying-glass" style="font-size:2rem;margin-bottom:1rem;opacity:0.4;display:block;"></i>
                    <p>No events found for <strong>"${searchInput.value}"</strong></p>
                    <p style="font-size:0.85rem;margin-top:0.5rem;">Try a different keyword or category filter.</p>`;
                eventsGrid.appendChild(noResultsEl);
            } else {
                noResultsEl.querySelector('p strong').textContent = `"${searchInput.value}"`;
            }
        } else if (noResultsEl) {
            noResultsEl.remove();
        }
    };

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(filterItems, 180);
        });
        // Also clear search on Escape key
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchInput.value = '';
                filterItems();
                searchInput.blur();
            }
        });
    }

    filterChips.forEach(chip => {
        chip.addEventListener('click', () => {
            filterChips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            filterItems();
        });
    });

    // Dynamic Event Registration
    const registerBtns = document.querySelectorAll('.register-btn');
    registerBtns.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const eventId = btn.getAttribute('data-event-id');
            const formLink = btn.getAttribute('data-form-link');
            if (!eventId) return;

            // If already registered/requested, just open the link
            if (btn.innerText.includes('Registered') || btn.innerText.includes('Requested')) {
                if (formLink) {
                    window.open(formLink, '_blank');
                }
                return;
            }

            // Loading state
            btn.classList.add('btn-loading');
            
            try {
                const response = await fetch('/register_event', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ event_id: eventId })
                });
                
                const result = await response.json();
                
                if (response.ok && result.status === 'success') {
                    // Success state
                    btn.classList.remove('btn-loading');
                    btn.classList.replace('btn-primary', 'btn-secondary');
                    btn.innerHTML = '<i class="fa-solid fa-clock"></i> Requested';
                    
                    // Redirect if Google Form link is present
                    if (result.redirect_url) {
                        window.open(result.redirect_url, '_blank');
                    }
                } else {
                    alert('Registration failed. Please try again.');
                    btn.classList.remove('btn-loading');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Network error. Please try again.');
                btn.classList.remove('btn-loading');
            }
        });
    });

    // Chat Interface Toggle logic
    const chatInterface = document.getElementById('demo-chat');
    const closeChatBtn = document.querySelector('.close-chat-btn');
    // Setup generic chat interface bindings natively
    const enrolledCards = document.querySelectorAll('.enrolled-club');

    let currentClubId = null;
    let chatPollInterval = null;
    let pollRequestId = 0; // To prevent race conditions
    const chatHistory = document.querySelector('.chat-history');
    const chatInput = document.querySelector('.chat-input-row input');
    const sendBtn = document.querySelector('.btn-send');

    if (enrolledCards && chatInterface) {
        enrolledCards.forEach(card => {
            card.style.cursor = 'pointer';
            card.addEventListener('click', (e) => {
                e.stopPropagation();

                // Remove active state from all enrolled club cards
                enrolledCards.forEach(c => c.classList.remove('active'));
                // Add active state to the clicked card
                card.classList.add('active');

                currentClubId = card.dataset.clubId;
                const clubName = card.dataset.clubName;
                
                chatInterface.classList.remove('hidden');
                document.getElementById('chat-club-name').textContent = clubName;
                
                // Clear and Poll immediately
                if (chatHistory) chatHistory.innerHTML = '<div class="chat-date-divider">Connecting to Live Server...</div>';
                pollChat();
                if (chatPollInterval) clearInterval(chatPollInterval);
                chatPollInterval = setInterval(pollChat, 3000); // Live poll 3s
            });
        });
    }

    if (closeChatBtn && chatInterface) {
        closeChatBtn.addEventListener('click', () => {
            chatInterface.classList.add('hidden');
            enrolledCards.forEach(c => c.classList.remove('active'));
            window.scrollBy({ top: -50, behavior: 'smooth' });
            if (chatPollInterval) clearInterval(chatPollInterval);
        });
    }

    function pollChat() {
        if (!currentClubId) return;
        const myRequestId = ++pollRequestId;
        fetch(`/api/chat/get?club_id=${encodeURIComponent(currentClubId)}`)
            .then(r => r.json())
            .then(data => {
                if (myRequestId !== pollRequestId) return; // Discard stale results
                if (data.messages && chatHistory) {
                   chatHistory.innerHTML = '';
                    data.messages.forEach(msg => {
                        const studentName = (document.querySelector('.header-user strong')?.textContent || 'User').trim();
                        const isSent = (msg.sender || "").trim() === studentName;
                        const msgHtml = `<div class="chat-msg ${isSent ? 'sent' : 'received'}"><strong>${msg.sender}</strong> ${msg.message}<span class="time">${msg.time}</span></div>`;
                       chatHistory.insertAdjacentHTML('beforeend', msgHtml);
                   });
                   // Optional: auto-scroll only if at bottom
                   chatHistory.scrollTop = chatHistory.scrollHeight;
                }
            }).catch(e => console.error("Chat poll err:", e));
            
        // Poll member count
        fetch(`/api/member_count?club_id=${encodeURIComponent(currentClubId)}`)
            .then(r => r.json())
            .then(data => {
                const countSpan = document.getElementById('chat-member-count');
                if (countSpan) countSpan.textContent = data.count;
            }).catch(e => console.error("Member err:", e));
    }

    const sendMessage = () => {
        if (!chatInput || !currentClubId) return;
        const msg = chatInput.value.trim();
        if (msg) {
            const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const studentName = document.querySelector('.header-user strong')?.textContent || 'User';
            
            fetch('/api/chat/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({club_id: currentClubId, sender: studentName, message: msg, time: time})
            }).then(() => {
                chatInput.value = '';
                pollChat();
            });
        }
    };

    if (sendBtn) {
        sendBtn.addEventListener('click', sendMessage);
    }
    if (chatInput) {
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    }

    // ========= Event Chat (Student) =========
    const eventChatPanel = document.getElementById('event-chat-panel');
    const eventChatHistoryEl = document.getElementById('event-chat-history-student');
    const eventChatInputEl = document.getElementById('event-chat-input-student');
    const eventChatSendStudentBtn = document.getElementById('event-chat-send-student');
    const closeEventChatBtn = document.getElementById('close-event-chat-btn');
    const eventChatEventNameEl = document.getElementById('event-chat-event-name');

    let currentEventId = null;
    let eventChatPollInterval = null;
    let eventPollRequestId = 0; // To prevent race conditions
    const studentName = (document.querySelector('.header-user strong')?.textContent || 'Student').trim();

    document.querySelectorAll('.event-chat-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            currentEventId = btn.getAttribute('data-event-id');
            const eventName = btn.getAttribute('data-event-name');
            if (eventChatEventNameEl) eventChatEventNameEl.textContent = eventName;
            if (eventChatPanel) eventChatPanel.classList.remove('hidden');
            if (eventChatHistoryEl) eventChatHistoryEl.innerHTML = '<div style="text-align:center;padding:1rem;color:#888;">Connecting...</div>';
            pollEventChatStudent();
            if (eventChatPollInterval) clearInterval(eventChatPollInterval);
            eventChatPollInterval = setInterval(pollEventChatStudent, 3000);
        }, true); // capture phase — fires before parent onclick
    });

    if (closeEventChatBtn) {
        closeEventChatBtn.addEventListener('click', () => {
            if (eventChatPanel) eventChatPanel.classList.add('hidden');
            if (eventChatPollInterval) clearInterval(eventChatPollInterval);
            currentEventId = null;
        });
    }

    function pollEventChatStudent() {
        if (!currentEventId || !eventChatHistoryEl) return;
        const myRequestId = ++eventPollRequestId;
        fetch(`/api/event_chat/get?event_id=${encodeURIComponent(currentEventId)}`)
            .then(r => r.json())
            .then(data => {
                if (myRequestId !== eventPollRequestId) return; // Discard stale results
                if (!data.messages || data.messages.length === 0) {
                    eventChatHistoryEl.innerHTML = '<div style="text-align:center;padding:1rem;color:#888;">No messages yet. Say hello!</div>';
                    return;
                }
                eventChatHistoryEl.innerHTML = '';
                data.messages.forEach(msg => {
                    const isSent = (msg.sender || "").trim() === studentName;
                    eventChatHistoryEl.insertAdjacentHTML('beforeend',
                        `<div class="chat-msg ${isSent ? 'sent' : 'received'}">
                            <strong>${msg.sender}</strong> ${msg.message}
                            <span class="time">${msg.time}</span>
                        </div>`
                    );
                });
                eventChatHistoryEl.scrollTop = eventChatHistoryEl.scrollHeight;
            }).catch(e => console.error('Event chat poll error:', e));
    }

    function sendEventChatMessage() {
        if (!eventChatInputEl || !currentEventId) return;
        const msg = eventChatInputEl.value.trim();
        if (!msg) return;
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        fetch('/api/event_chat/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_id: currentEventId, sender: studentName, message: msg, time: time })
        }).then(() => {
            eventChatInputEl.value = '';
            pollEventChatStudent();
        });
    }

    if (eventChatSendStudentBtn) {
        eventChatSendStudentBtn.addEventListener('click', sendEventChatMessage);
    }
    if (eventChatInputEl) {
        eventChatInputEl.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendEventChatMessage();
        });
    }
});
