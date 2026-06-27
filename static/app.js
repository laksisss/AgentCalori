const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

let telegramId = null;
try {
    const initData = new URLSearchParams(tg.initData);
    const userJson = initData.get('user');
    if (userJson) {
        const user = JSON.parse(userJson);
        telegramId = user.id;
    }
} catch (e) {
    console.error('Ошибка парсинга initData:', e);
}

let currentDate = new Date();

const caloriesProgress = document.getElementById('caloriesProgress');
const caloriesCurrent = document.getElementById('caloriesCurrent');
const caloriesGoal = document.getElementById('caloriesGoal');
const proteinBar = document.getElementById('proteinBar');
const proteinCurrent = document.getElementById('proteinCurrent');
const proteinGoal = document.getElementById('proteinGoal');
const fatBar = document.getElementById('fatBar');
const fatCurrent = document.getElementById('fatCurrent');
const fatGoal = document.getElementById('fatGoal');
const carbsBar = document.getElementById('carbsBar');
const carbsCurrent = document.getElementById('carbsCurrent');
const carbsGoal = document.getElementById('carbsGoal');
const mealsList = document.getElementById('mealsList');
const currentDateEl = document.getElementById('currentDate');
const addMealBtn = document.getElementById('addMealBtn');

function formatDate(date) {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.toDateString() === today.toDateString()) return 'Сегодня';
    if (date.toDateString() === yesterday.toDateString()) return 'Вчера';
    return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
}

function dateToString(date) {
    return date.toISOString().split('T')[0];
}

const MEAL_TYPE_NAMES = {
    'breakfast': '🍳 Завтрак',
    'lunch': '🍽 Обед',
    'dinner': '🌙 Ужин',
    'snack': '🍎 Перекус'
};

function updateMacro(bar, currentEl, goalEl, current, goal) {
    const percent = Math.min((current / goal) * 100, 100);
    bar.style.width = percent + '%';
    currentEl.textContent = Math.round(current);
    goalEl.textContent = goal;
}

function renderMeals(meals) {
    if (!meals || meals.length === 0) {
        mealsList.innerHTML = '<div class="empty">Пока пусто. Отправь фото или текст боту!</div>';
        return;
    }
    mealsList.innerHTML = meals.map(meal => `
        <div class="meal-card">
            <div class="meal-info">
                <div class="meal-name">
                    ${meal.name}
                    <span class="meal-type-badge">${MEAL_TYPE_NAMES[meal.meal_type] || meal.meal_type}</span>
                </div>
                <div class="meal-details">
                    ${meal.weight}г · Б:${meal.protein}г Ж:${meal.fat}г У:${meal.carbs}г
                </div>
            </div>
            <div class="meal-calories">${Math.round(meal.calories)} ккал</div>
        </div>
    `).join('');
}

async function loadStats() {
    if (!telegramId) {
        mealsList.innerHTML = '<div class="empty">Ошибка: не удалось определить пользователя</div>';
        return;
    }

    const dateStr = dateToString(currentDate);
    currentDateEl.textContent = formatDate(currentDate);

    try {
        const [statsRes, mealsRes] = await Promise.all([
            fetch(`/api/stats/${telegramId}?date=${dateStr}`),
            fetch(`/api/meals/${telegramId}?date=${dateStr}`)
        ]);

        const stats = await statsRes.json();
        const meals = await mealsRes.json();

        const calPercent = Math.min((stats.calories / stats.goal.calories) * 100, 100);
        const circumference = 2 * Math.PI * 52;
        const offset = circumference - (calPercent / 100) * circumference;
        caloriesProgress.style.strokeDashoffset = offset;
        caloriesCurrent.textContent = Math.round(stats.calories);
        caloriesGoal.textContent = stats.goal.calories;

        updateMacro(proteinBar, proteinCurrent, proteinGoal, stats.protein, stats.goal.protein);
        updateMacro(fatBar, fatCurrent, fatGoal, stats.fat, stats.goal.fat);
        updateMacro(carbsBar, carbsCurrent, carbsGoal, stats.carbs, stats.goal.carbs);

        renderMeals(meals);
    } catch (error) {
        console.error('Ошибка загрузки:', error);
        mealsList.innerHTML = '<div class="empty">Ошибка загрузки данных</div>';
    }
}

document.getElementById('prevDay').addEventListener('click', () => {
    currentDate.setDate(currentDate.getDate() - 1);
    loadStats();
});

document.getElementById('nextDay').addEventListener('click', () => {
    const today = new Date();
    if (currentDate < today) {
        currentDate.setDate(currentDate.getDate() + 1);
        loadStats();
    }
});

addMealBtn.addEventListener('click', () => {
    // Закрываем Mini App, чтобы пользователь мог отправить еду боту
    tg.close();
});

tg.onEvent('themeChanged', () => loadStats());

loadStats();

document.addEventListener('visibilitychange', () => {
    if (!document.hidden) loadStats();
});
