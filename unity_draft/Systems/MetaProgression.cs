using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Meta progression: coin bank, run coins, kill counter, coupons, consumables, wanted poster.
    /// Keep this light-weight until a full save system lands.
    /// </summary>
    public class MetaProgression : MonoBehaviour
    {
        [Header("Coins / Banking")]
        public int bankedCoins = 0;   // persistent bank
        public int runCoins = 0;      // earned in current run
        public int bankCap = 999999;
        public float bankInterestRate = 0.02f; // simple interest on carry-over
        public int bankInterestLevelGate = 3;

        [Header("Progress")]
        public int killCount = 0;
        public int coupons = 0;
        public int couponCap = 99;
        public int killsPerCoupon = 50;

        [Header("Wanted Poster")]
        public bool wantedActive = false;
        public int wantedBounty = 0;
        public int wantedKillTarget = 0;

        [Header("Consumables")]
        [System.Serializable]
        public class ConsumableStack
        {
            public string id;
            public int count;

            public ConsumableStack(string id, int count)
            {
                this.id = id;
                this.count = count;
            }
        }

        public List<ConsumableStack> consumables = new();

        public void AddRunCoins(int amount) => runCoins = Mathf.Max(0, runCoins + Mathf.Max(0, amount));
        public void SpendRunCoins(int amount) => runCoins = Mathf.Max(0, runCoins - Mathf.Max(0, amount));

        public void BankRunCoins()
        {
            bankedCoins = Mathf.Clamp(bankedCoins + runCoins, 0, bankCap);
            runCoins = 0;
        }

        public void AddBankedCoins(int amount) => bankedCoins = Mathf.Clamp(bankedCoins + Mathf.Max(0, amount), 0, bankCap);

        public void SpendBankedCoins(int amount) => bankedCoins = Mathf.Max(0, bankedCoins - Mathf.Max(0, amount));

        public void AddKill(int amount = 1)
        {
            int add = Mathf.Max(0, amount);
            killCount += add;
            // Coupon reward on thresholds
            if (killsPerCoupon > 0)
            {
                int couponsAward = killCount / killsPerCoupon;
                AddCoupon(couponsAward);
            }
            // Wanted poster completion
            if (WantedSatisfied() && wantedBounty > 0)
            {
                AddRunCoins(wantedBounty);
                ClearWanted();
            }
        }

        public void OnLevelComplete(int levelIdx)
        {
            BankRunCoins();
            ClearWanted(); // wanted poster resets on success by default
            // Simple bank interest after level gate
            if (levelIdx + 1 >= bankInterestLevelGate && bankInterestRate > 0f)
            {
                int interest = Mathf.FloorToInt(bankedCoins * bankInterestRate);
                AddBankedCoins(interest);
            }
        }

        public void AddCoupon(int amount = 1) => coupons = Mathf.Clamp(coupons + Mathf.Max(0, amount), 0, couponCap);

        public void ActivateWanted(int bounty)
        {
            wantedActive = true;
            wantedBounty = Mathf.Max(0, bounty);
            wantedKillTarget = Mathf.Max(wantedKillTarget, bounty);
        }

        public void ClearWanted()
        {
            wantedActive = false;
            wantedBounty = 0;
            wantedKillTarget = 0;
        }

        public int ConsumeCoupons(int count)
        {
            int use = Mathf.Min(count, coupons);
            coupons -= use;
            return use;
        }

        public void AddConsumable(string id, int count = 1)
        {
            var stack = consumables.Find(c => c.id == id);
            if (stack == null)
            {
                consumables.Add(new ConsumableStack(id, Mathf.Max(1, count)));
            }
            else
            {
                stack.count += Mathf.Max(1, count);
            }
        }

        public bool UseConsumable(string id)
        {
            var stack = consumables.Find(c => c.id == id);
            if (stack == null || stack.count <= 0) return false;
            stack.count--;
            return true;
        }

        public bool WantedSatisfied()
        {
            return wantedActive && killCount >= wantedKillTarget && wantedKillTarget > 0;
        }
    }
}
