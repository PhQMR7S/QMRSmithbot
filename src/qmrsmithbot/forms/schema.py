"""Forward-only form paths: no arbitrary code, expressions or unbounded loops."""
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Choice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(min_length=1, max_length=64)
    next: str | None = Field(default=None, max_length=16)


class Question(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,15}$')
    prompt: str = Field(min_length=1, max_length=500)
    kind: Literal['text','number','choice'] = 'text'
    required: bool = True
    minimum: float | None = Field(default=None, ge=-1e9, le=1e9)
    maximum: float | None = Field(default=None, ge=-1e9, le=1e9)
    choices: list[Choice] = Field(default_factory=list, max_length=8)

    @model_validator(mode='after')
    def validate_question(self):
        if self.id == 'end' or not self.prompt.strip():
            raise ValueError('Invalid question')
        if self.kind == 'choice':
            labels = [c.label.strip() for c in self.choices]
            if len(labels)<2 or any(not label for label in labels) or len(set(labels))!=len(labels):
                raise ValueError('Provide 2–8 distinct choices')
        elif self.choices:
            raise ValueError('Only choice questions accept choices')
        if self.kind != 'number' and (self.minimum is not None or self.maximum is not None):
            raise ValueError('Number limits require a number question')
        if self.minimum is not None and self.maximum is not None and self.minimum>self.maximum:
            raise ValueError('Minimum exceeds maximum')
        return self


class Form(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=100)
    completion: str = Field(default='✅ تم حفظ إجاباتك. شكرًا لك.',min_length=1,max_length=1000)
    questions: list[Question] = Field(min_length=1,max_length=20)

    @model_validator(mode='after')
    def validate_paths(self):
        if not self.title.strip() or not self.completion.strip():
            raise ValueError('Blank form text')
        positions = {q.id:i for i,q in enumerate(self.questions)}
        if len(positions)!=len(self.questions):
            raise ValueError('Question IDs must be unique')
        for i, question in enumerate(self.questions):
            for choice in question.choices:
                if choice.next is not None and choice.next!='end' and positions.get(choice.next,-1)<=i:
                    raise ValueError('Branches must point to a later question or end')
        return self

    def after(self, question_id, choice=None):
        index = next(i for i,q in enumerate(self.questions) if q.id==question_id)
        question = self.questions[index]
        target = question.choices[choice].next if choice is not None else None
        if target == 'end':
            return None
        return target or (self.questions[index+1].id if index+1<len(self.questions) else None)


def validate_answer(question, text):
    if not text.strip() or len(text)>1000:
        raise ValueError('أرسل إجابة نصية من 1 إلى 1000 حرف.')
    if question.kind=='number':
        try:
            number = Decimal(text.strip())
        except InvalidOperation:
            raise ValueError('أرسل رقمًا صحيح الصيغة، مثل 12 أو 12.5.') from None
        if not number.is_finite() or number.copy_abs()>Decimal('1e9'):
            raise ValueError('أرسل رقمًا محدودًا بين -1000000000 و1000000000.')
        if question.minimum is not None and number<Decimal(str(question.minimum)):
            raise ValueError(f'أقل قيمة مقبولة: {question.minimum:g}.')
        if question.maximum is not None and number>Decimal(str(question.maximum)):
            raise ValueError(f'أعلى قيمة مقبولة: {question.maximum:g}.')
    return text.strip()


def default_form(language='ar'):
    if language=='en':
        return Form(title='Contact form',completion='✅ Your answers have been saved. Thank you.',questions=[
            Question(id='name',prompt='What is your name?'),Question(id='request',prompt='How can we help you?')])
    return Form(title='نموذج التواصل',questions=[Question(id='name',prompt='ما اسمك؟'),
        Question(id='request',prompt='كيف نقدر نساعدك؟')])
