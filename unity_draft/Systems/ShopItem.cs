using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    public enum ShopItemType
    {
        Upgrade,
        Consumable,
        Coupon
    }

    [CreateAssetMenu(fileName = "ShopItem", menuName = "ZGame/ShopItem")]
    public class ShopItem : ScriptableObject
    {
        public string itemId;
        public string displayName;
        public ShopItemType type = ShopItemType.Upgrade;
        public int baseCost = 50;
        public string description;
        public UpgradeEffect upgradeEffect = UpgradeEffect.Attack;

        [Header("Effect")]
        public int addAttack = 0;
        public float addSpeed = 0f;
        public float addRangeMult = 0f;
        public int addShield = 0;
        public int addCoupons = 0;
        public int addBankedCoins = 0;
        public int addRunCoins = 0;
        public int addKills = 0;
        public bool activateWanted = false;
        public int wantedBounty = 0;
        [Header("Consumable")]
        public string consumableId;
        public int consumableCount = 0;
        public string consumableEffect; // optional effect ID
    }
}
