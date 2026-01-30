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
        public GameObject startPanel;
        public GameObject endPanel;
        [Header("Level-Up Picker")]
        public UnityEvent<int> onLevelUpChoice;
        public TMPro.TextMeshProUGUI levelUpTitle;
        public TMPro.TextMeshProUGUI[] levelUpOptionTexts;
        public TMPro.TextMeshProUGUI[] levelUpOptionDescTexts;
        [Header("Buttons (optional wiring)")]
        public UnityEngine.UI.Button pauseButton;
        public UnityEngine.UI.Button resumeButton;
        public UnityEngine.UI.Button successContinueButton;
        public UnityEngine.UI.Button failRetryButton;
        public UnityEngine.UI.Button homeButton;
        public UnityEngine.UI.Button[] levelUpOptionButtons;
        public UnityEngine.UI.Button startContinueButton;
        public UnityEngine.UI.Button endContinueButton;
        [Header("Data Bindings (optional)")]
        public TMPro.TextMeshProUGUI coinsText;
        public TMPro.TextMeshProUGUI couponsText;
        public TMPro.TextMeshProUGUI killsText;
        public TMPro.TextMeshProUGUI levelText;
        public TMPro.TextMeshProUGUI wantedText;
        public TMPro.TextMeshProUGUI pauseInfoText;
        public TMPro.TextMeshProUGUI successInfoText;
        public TMPro.TextMeshProUGUI failInfoText;
        [Header("Inventory / Reroll UI")]
        public UnityEngine.UI.Button rerollButton;
        public TMPro.TextMeshProUGUI rerollCostText;

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

        public void ShowStartSequence()
        {
            if (startPanel != null) startPanel.SetActive(true);
        }

        public void HideStartSequence()
        {
            if (startPanel != null) startPanel.SetActive(false);
        }

        public void ShowEndSequence()
        {
            if (endPanel != null) endPanel.SetActive(true);
        }

        public void HideEndSequence()
        {
            if (endPanel != null) endPanel.SetActive(false);
        }

        public void BindLevelUpOptions(string title, string[] options, string[] descs = null)
        {
            if (levelUpTitle != null) levelUpTitle.text = title;
            if (levelUpOptionTexts != null && options != null)
            {
                for (int i = 0; i < levelUpOptionTexts.Length; i++)
                {
                    levelUpOptionTexts[i].text = i < options.Length ? options[i] : string.Empty;
                    if (levelUpOptionDescTexts != null && i < levelUpOptionDescTexts.Length && descs != null)
                    {
                        levelUpOptionDescTexts[i].text = i < descs.Length ? descs[i] : string.Empty;
                    }
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

        public void BindRerollCost(int cost)
        {
            if (rerollCostText != null) rerollCostText.text = $"Reroll: {cost}";
        }

        private void WireButtons()
        {
            if (pauseButton) { pauseButton.onClick.RemoveAllListeners(); pauseButton.onClick.AddListener(Pause); }
            if (resumeButton) { resumeButton.onClick.RemoveAllListeners(); resumeButton.onClick.AddListener(Resume); }
            if (successContinueButton) { successContinueButton.onClick.RemoveAllListeners(); successContinueButton.onClick.AddListener(Resume); }
            if (failRetryButton) { failRetryButton.onClick.RemoveAllListeners(); failRetryButton.onClick.AddListener(Restart); }
            if (homeButton) { homeButton.onClick.RemoveAllListeners(); homeButton.onClick.AddListener(Home); }
            if (startContinueButton) { startContinueButton.onClick.RemoveAllListeners(); startContinueButton.onClick.AddListener(HideStartSequence); }
            if (endContinueButton) { endContinueButton.onClick.RemoveAllListeners(); endContinueButton.onClick.AddListener(HideEndSequence); }
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

        public void BindMeta(ZGame.UnityDraft.Systems.MetaProgression meta, ZGame.UnityDraft.Systems.GameManager gm)
        {
            if (coinsText) coinsText.text = meta != null ? meta.runCoins.ToString() : "0";
            if (couponsText) couponsText.text = meta != null ? meta.coupons.ToString() : "0";
            if (killsText) killsText.text = meta != null ? meta.killCount.ToString() : "0";
            if (levelText) levelText.text = gm != null ? (gm.currentLevelIndex + 1).ToString() : "-";
            if (wantedText && meta != null)
            {
                wantedText.text = meta.wantedActive ? $"Wanted {meta.wantedBounty}" : "Wanted: None";
            }
            if (pauseInfoText && gm != null)
            {
                pauseInfoText.text = $"Level {gm.currentLevelIndex + 1}";
            }
            if (successInfoText && gm != null)
            {
                successInfoText.text = $"Completed Level {gm.currentLevelIndex + 1}";
            }
            if (failInfoText && gm != null)
            {
                failInfoText.text = $"Failed Level {gm.currentLevelIndex + 1}";
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
