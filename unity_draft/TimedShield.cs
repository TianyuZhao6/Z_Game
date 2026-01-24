using UnityEngine;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Tracks shield duration and clears shieldHp on expiry.
    /// </summary>
    public class TimedShield : MonoBehaviour
    {
        private Enemy _enemy;
        private float _t;
        private float _duration;
        private int _amount;

        private void Awake()
        {
            _enemy = GetComponent<Enemy>();
        }

        public void SetShield(int amount, float duration)
        {
            _amount = amount;
            _duration = duration;
            _t = 0f;
            if (_enemy != null)
            {
                _enemy.shieldHp = Mathf.Max(_enemy.shieldHp, amount);
            }
        }

        private void Update()
        {
            if (_enemy == null) return;
            if (_enemy.shieldHp <= 0) { enabled = false; return; }
            _t += Time.deltaTime;
            if (_t >= _duration)
            {
                _enemy.shieldHp = 0;
                enabled = false;
            }
        }
    }
}
