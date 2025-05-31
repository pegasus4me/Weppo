document.addEventListener('DOMContentLoaded', () => {
    const ticketList = document.getElementById('ticketList');

    async function fetchTickets() {
        try {
            const response = await fetch('/api/tickets');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const tickets = await response.json();
            renderTickets(tickets);
        } catch (error) {
            console.error("Failed to fetch tickets:", error);
            ticketList.innerHTML = '<p>Error loading tickets. Please try again later.</p>';
        }
    }

    function renderTickets(tickets) {
        ticketList.innerHTML = ''; // Clear existing tickets

        if (tickets.length === 0) {
            ticketList.innerHTML = '<p>No tickets found.</p>';
            return;
        }

        tickets.forEach(ticket => {
            const listItem = document.createElement('li');
            listItem.classList.add('ticket-item');
            listItem.setAttribute('id', `ticket-${ticket.id}`);

            let conversationHtml = '<p>No conversation history.</p>';
            if (ticket.conversation_history && ticket.conversation_history.length > 0) {
                conversationHtml = ticket.conversation_history.map(msg => `<p>${escapeHtml(msg)}</p>`).join('');
            }

            listItem.innerHTML = `
                <h3>Ticket ID: ${escapeHtml(ticket.id)}</h3>
                <p><strong>User Query:</strong> ${escapeHtml(ticket.user_query)}</p>
                <p><strong>Timestamp:</strong> ${new Date(ticket.timestamp).toLocaleString()}</p>
                <p><strong>Status:</strong> <span class="status ${ticket.status.toLowerCase()}">${escapeHtml(ticket.status.toUpperCase())}</span></p>
                <p><strong>Conversation History:</strong></p>
                <div class="conversation-history">${conversationHtml}</div>
                <div class="actions">
                    <select id="status-select-${ticket.id}">
                        <option value="open" ${ticket.status === 'open' ? 'selected' : ''}>Open</option>
                        <option value="closed" ${ticket.status === 'closed' ? 'selected' : ''}>Closed</option>
                        <option value="pending" ${ticket.status === 'pending' ? 'selected' : ''}>Pending</option>
                        <!-- Add more statuses as needed -->
                    </select>
                    <button onclick="updateTicketStatus('${ticket.id}')">Update Status</button>
                </div>
            `;
            ticketList.appendChild(listItem);
        });
    }

    async function updateTicketStatus(ticketId) {
        const statusSelect = document.getElementById(`status-select-${ticketId}`);
        const newStatus = statusSelect.value;

        if (!newStatus) {
            alert('Please select a status.');
            return;
        }

        try {
            const response = await fetch(`/api/tickets/${ticketId}/status`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ status: newStatus }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`HTTP error! status: ${response.status}, Detail: ${errorData.detail}`);
            }

            // Optimistically update the UI or refetch
            // For simplicity, refetch all tickets
            fetchTickets();
            // Or, more efficiently, update just the changed ticket in the DOM
            // const updatedTicket = await response.json();
            // updateTicketInDOM(updatedTicket);

        } catch (error) {
            console.error("Failed to update ticket status:", error);
            alert(`Error updating ticket: ${error.message}`);
        }
    }

    // Make updateTicketStatus globally accessible for the inline onclick handler
    window.updateTicketStatus = updateTicketStatus;

    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    // Initial fetch of tickets
    fetchTickets();
});
