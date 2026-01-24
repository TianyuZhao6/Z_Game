using UnityEngine;
using UnityEngine.Events;
using UnityEngine.UI;

namespace ZGame.UnityDraft.UI
{
    /// <summary>
    /// Placeholder pause/success/fail/level-up menus. Wire actual UI here.
    /// </summary>
    public class MenuController : MonoBehaviour
    {
        public UnityEvent onPause;
        public UnityEvent onResume;
        public UnityEvent onSuccess;
        public UnityEvent onFail;
        public UnityEvent onLevelUp;
        public UnityEvent onRestart;
        public UnityEvent onHome;
        public UnityEvent onShopClosed;
        [Header("Panels")]
        public GameObject pausePanel;
        public GameObject successPanel;
        public GameObject failPanel;
        public GameObject levelUpPanel;
        public GameObject shopPanel;
        [Header("Level-Up Picker")]
        public UnityEvent<int> onLevelUpChoice;
        public TMPro.TextMeshProUGUI levelUpTitle;
        public TMPro.TextMeshProUGUI[] levelUpOptionTexts;
        [Header("Buttons (optional wiring)")]
        public UnityEngine.UI.Button pauseButton;
        public UnityEngine.UI.Button resumeButton;
        public UnityEngine.UI.Button successContinueButton;
        public UnityEngine.UI.Button failRetryButton;
        public UnityEngine.UI.Button homeButton;
        public UnityEngine.UI.Button[] levelUpOptionButtons;

        private void Start()
        {
            WireButtons();
        }

        public void Pause()
        {
            onPause?.Invoke();
            Time.timeScale = 0f;
            if (pausePanel != null) pausePanel.SetActive(true);
        }

        public void Resume()
        {
            Time.timeScale = 1f;
            onResume?.Invoke();
            if (pausePanel != null) pausePanel.SetActive(false);
            if (shopPanel != null && shopPanel.activeSelf) shopPanel.SetActive(false);
        }

        public void ShowSuccess()
        {
            onSuccess?.Invoke();
            if (successPanel != null) successPanel.SetActive(true);
        }

        public void ShowFail()
        {
            onFail?.Invoke();
            if (failPanel != null) failPanel.SetActive(true);
        }

        public void ShowLevelUp()
        {
            onLevelUp?.Invoke();
            if (levelUpPanel != null) levelUpPanel.SetActive(true);
        }

        public void BindLevelUpOptions(string title, string[] options)
        {
            if (levelUpTitle != null) levelUpTitle.text = title;
            if (levelUpOptionTexts != null && options != null)
            {
                for (int i = 0; i < levelUpOptionTexts.Length; i++)
                {
                    levelUpOptionTexts[i].text = i < options.Length ? options[i] : string.Empty;
                }
            }
        }

        public void ChooseLevelUpOption(int index)
        {
            onLevelUpChoice?.Invoke(index);
            if (levelUpPanel != null) levelUpPanel.SetActive(false);
        }

        public void Restart()
        {
            onRestart?.Invoke();
            if (successPanel != null) successPanel.SetActive(false);
            if (failPanel != null) failPanel.SetActive(false);
        }

        public void Home()
        {
            onHome?.Invoke();
            if (successPanel != null) successPanel.SetActive(false);
            if (failPanel != null) failPanel.SetActive(false);
        }

        public void CloseShop()
        {
            onShopClosed?.Invoke();
            if (shopPanel != null) shopPanel.SetActive(false);
        }

        private void WireButtons()
        {
            if (pauseButton) { pauseButton.onClick.RemoveAllListeners(); pauseButton.onClick.AddListener(Pause); }
            if (resumeButton) { resumeButton.onClick.RemoveAllListeners(); resumeButton.onClick.AddListener(Resume); }
            if (successContinueButton) { successContinueButton.onClick.RemoveAllListeners(); successContinueButton.onClick.AddListener(Resume); }
            if (failRetryButton) { failRetryButton.onClick.RemoveAllListeners(); failRetryButton.onClick.AddListener(Restart); }
            if (homeButton) { homeButton.onClick.RemoveAllListeners(); homeButton.onClick.AddListener(Home); }
            if (levelUpOptionButtons != null && levelUpOptionButtons.Length > 0)
            {
                for (int i = 0; i < levelUpOptionButtons.Length; i++)
                {
                    int idx = i;
                    levelUpOptionButtons[i].onClick.RemoveAllListeners();
                    levelUpOptionButtons[i].onClick.AddListener(() => ChooseLevelUpOption(idx));
                }
            }
        }

        // Input hook: call from Update if you want ESC to pause/resume (Python-like behavior).
        public void TogglePause()
        {
            if (Mathf.Approximately(Time.timeScale, 0f))
            {
                Resume();
            }
            else
            {
                Pause();
            }
        }
    }
}
