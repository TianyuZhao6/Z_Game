using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    public enum UpgradeEffect
    {
        Attack,
        Speed,
        RangeMult,
        Shield,
        CritChance,
        CritMult,
        BonePlating,
        Carapace,
        Coupon,
        WantedBounty,
        RunCoins,
        BankCoins
    }

    [CreateAssetMenu(fileName = "UpgradeDef", menuName = "ZGame/Upgrade")]
    public class UpgradeDef : ScriptableObject
    {
        public string id;
        public string displayName;
        [TextArea] public string description;
        public UpgradeEffect effect;
        public float value;
    }
}
