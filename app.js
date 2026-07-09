document.addEventListener('DOMContentLoaded', () => {
  
  // ==========================================================================
  // Interactive Financial Charts (Chart.js)
  // ==========================================================================
  
  // 1. Line Chart: Portfolio Growth
  const ctxPortfolio = document.getElementById('portfolioChart');
  if (ctxPortfolio) {
    const chartGradient = ctxPortfolio.getContext('2d').createLinearGradient(0, 0, 0, 150);
    chartGradient.addColorStop(0, 'rgba(16, 185, 129, 0.25)');
    chartGradient.addColorStop(1, 'rgba(16, 185, 129, 0.0)');

    new Chart(ctxPortfolio, {
      type: 'line',
      data: {
        labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'],
        datasets: [{
          label: 'Portfolio Value ($)',
          data: [54000, 58200, 61000, 68900, 72000, 78400, 82140],
          borderColor: '#10B981',
          borderWidth: 2,
          pointBackgroundColor: '#10B981',
          pointHoverRadius: 5,
          tension: 0.35,
          fill: true,
          backgroundColor: chartGradient,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: 'index',
            intersect: false,
            backgroundColor: '#081A2F',
            titleFont: { family: 'Inter', size: 10, weight: '600' },
            bodyFont: { family: 'Inter', size: 11 },
            borderColor: 'rgba(255, 255, 255, 0.08)',
            borderWidth: 1,
            displayColors: false,
            padding: 8
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: 'rgba(255, 255, 255, 0.4)',
              font: { family: 'Inter', size: 9 }
            }
          },
          y: {
            grid: {
              color: 'rgba(255, 255, 255, 0.04)',
              drawBorder: false
            },
            ticks: {
              color: 'rgba(255, 255, 255, 0.4)',
              font: { family: 'Inter', size: 9 },
              callback: (value) => '$' + (value / 1000) + 'k'
            }
          }
        }
      }
    });
  }

  // 2. Doughnut Chart: Expenses Breakdown
  const ctxExpense = document.getElementById('expenseChart');
  if (ctxExpense) {
    new Chart(ctxExpense, {
      type: 'doughnut',
      data: {
        labels: ['SaaS', 'Housing', 'Investing', 'General'],
        datasets: [{
          data: [25, 45, 20, 10],
          backgroundColor: [
            '#10B981', // Emerald Primary Accent
            '#12395F', // Deep Blue
            '#22C55E', // Success Green
            '#F59E0B'  // Warning Amber
          ],
          borderColor: 'rgba(8, 26, 47, 0.8)',
          borderWidth: 1.5
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '72%',
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#081A2F',
            titleFont: { family: 'Inter', size: 10 },
            bodyFont: { family: 'Inter', size: 11 },
            borderColor: 'rgba(255, 255, 255, 0.08)',
            borderWidth: 1,
            padding: 6,
            callbacks: {
              label: (context) => ` ${context.label}: ${context.raw}%`
            }
          }
        }
      }
    });
  }

  // ==========================================================================
  // Password Visibility Toggle
  // ==========================================================================
  const passwordInput = document.getElementById('password');
  const passwordToggle = document.getElementById('passwordToggle');
  const eyeIcon = passwordToggle ? passwordToggle.querySelector('.icon-eye') : null;
  const eyeOffIcon = passwordToggle ? passwordToggle.querySelector('.icon-eye-off') : null;

  if (passwordToggle && passwordInput) {
    passwordToggle.addEventListener('click', () => {
      const isPassword = passwordInput.getAttribute('type') === 'password';
      passwordInput.setAttribute('type', isPassword ? 'text' : 'password');
      
      if (isPassword) {
        eyeIcon.style.display = 'none';
        eyeOffIcon.style.display = 'block';
      } else {
        eyeIcon.style.display = 'block';
        eyeOffIcon.style.display = 'none';
      }
    });
  }

  // ==========================================================================
  // Form Validation & Submission Handling
  // ==========================================================================
  const loginForm = document.getElementById('loginForm');
  const emailInput = document.getElementById('email');
  const emailError = document.getElementById('emailError');
  const passwordError = document.getElementById('passwordError');
  const globalError = document.getElementById('globalError');
  const submitBtn = document.getElementById('submitBtn');
  const btnText = submitBtn ? submitBtn.querySelector('.btn-text') : null;
  const btnSpinner = submitBtn ? submitBtn.querySelector('.btn-spinner') : null;

  if (loginForm) {
    loginForm.addEventListener('submit', (e) => {
      e.preventDefault();
      
      // Clear previous error messages
      resetValidationState();
      
      let isValid = true;
      
      // Email verification
      const emailValue = emailInput.value.trim();
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailValue) {
        showError(emailInput, emailError, 'Email address is required.');
        isValid = false;
      } else if (!emailRegex.test(emailValue)) {
        showError(emailInput, emailError, 'Enter a valid email address.');
        isValid = false;
      }
      
      // Password verification
      const passwordValue = passwordInput.value;
      if (!passwordValue) {
        showError(passwordInput, passwordError, 'Password is required.');
        isValid = false;
      } else if (passwordValue.length < 8) {
        showError(passwordInput, passwordError, 'Password must be at least 8 characters.');
        isValid = false;
      }
      
      if (!isValid) {
        globalError.style.display = 'flex';
        globalError.className = 'form-alert error';
        globalError.querySelector('.alert-message').textContent = 'Please correct the highlighted errors.';
        return;
      }
      
      // Simulate high-fidelity authentication flow
      executeSecureLogin();
    });
  }

  function showError(input, errorElement, message) {
    input.classList.add('input-error');
    errorElement.textContent = message;
    errorElement.style.display = 'block';
  }

  function resetValidationState() {
    emailInput.classList.remove('input-error');
    passwordInput.classList.remove('input-error');
    emailError.style.display = 'none';
    passwordError.style.display = 'none';
    globalError.style.display = 'none';
  }

  function executeSecureLogin() {
    // Disable elements and display loading spinner
    submitBtn.disabled = true;
    emailInput.disabled = true;
    passwordInput.disabled = true;
    passwordToggle.disabled = true;
    btnText.style.opacity = '0';
    btnSpinner.style.display = 'block';
    
    // Simulate server side verification delay
    setTimeout(() => {
      // Simulate success callback
      btnSpinner.style.display = 'none';
      submitBtn.classList.remove('btn-primary');
      submitBtn.style.backgroundColor = '#22C55E'; // Success green token
      submitBtn.style.borderColor = '#22C55E';
      btnText.textContent = 'Authenticated Successfully';
      btnText.style.opacity = '1';
      
      // Show high fidelity success indicator on card
      globalError.style.display = 'flex';
      globalError.className = 'form-alert success';
      globalError.querySelector('.alert-message').textContent = 'Access granted. Initializing secure console...';
      
      // Optional: Redirection simulation
      setTimeout(() => {
        alert('Simulation Complete: In a production app, the user would now be securely logged in and redirected to their active session dashboard.');
        // Enable back inputs to test again
        submitBtn.disabled = false;
        emailInput.disabled = false;
        passwordInput.disabled = false;
        passwordToggle.disabled = false;
        submitBtn.style.backgroundColor = '';
        submitBtn.style.borderColor = '';
        submitBtn.classList.add('btn-primary');
        btnText.textContent = 'Sign In to Dashboard';
        resetValidationState();
        emailInput.value = '';
        passwordInput.value = '';
      }, 2000);
      
    }, 1800);
  }
});
