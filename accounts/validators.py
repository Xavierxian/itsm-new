from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError


class UserAttributeSimilarityValidator(password_validation.UserAttributeSimilarityValidator):
    def validate(self, password, user=None):
        try:
            return super().validate(password, user)
        except ValidationError as exc:
            raise ValidationError("密码与账户信息过于相似，请更换。", code=exc.code)

    def get_help_text(self):
        return "密码不能与用户名、姓名或邮箱等账户信息过于相似。"


class MinimumLengthValidator(password_validation.MinimumLengthValidator):
    def validate(self, password, user=None):
        try:
            return super().validate(password, user)
        except ValidationError as exc:
            raise ValidationError(f"密码长度不能少于 {self.min_length} 个字符。", code=exc.code)

    def get_help_text(self):
        return f"密码长度不能少于 {self.min_length} 个字符。"


class CommonPasswordValidator(password_validation.CommonPasswordValidator):
    def validate(self, password, user=None):
        try:
            return super().validate(password, user)
        except ValidationError as exc:
            raise ValidationError("该密码过于常见，请使用更复杂的密码。", code=exc.code)

    def get_help_text(self):
        return "密码不能使用过于常见的组合。"


class NumericPasswordValidator(password_validation.NumericPasswordValidator):
    def validate(self, password, user=None):
        try:
            return super().validate(password, user)
        except ValidationError as exc:
            raise ValidationError("密码不能是纯数字。", code=exc.code)

    def get_help_text(self):
        return "密码不能设置为纯数字。"
