from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
from datetime import date, timedelta
from uuid import uuid4
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from models import Base, TransactionORM

import os

# Ensure data folder exists
os.makedirs("data", exist_ok=True)

# Database setup
DB_PATH = "sqlite:///./data/finance.db"
engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# FastAPI App
app = FastAPI()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic Models
class TransactionCreate(BaseModel):
    category: str
    amount: float
    date: date
    type: Literal["income", "expense"]
    recurring: str

class TransactionOut(TransactionCreate):
    id: str

# Routes
@app.get("/transactions/", response_model=List[TransactionOut])
def list_transactions(days: int = 0, db: Session = Depends(get_db)):
    query = db.query(TransactionORM)
    if days:
        cutoff = date.today() - timedelta(days=days)
        query = query.filter(TransactionORM.date >= cutoff)
    txs = query.order_by(TransactionORM.date.desc()).all()
    return txs
  
@app.post("/transactions/", response_model=TransactionCreate)
def add_transaction(tx: TransactionCreate, db: Session = Depends(get_db)):
    new_tx = TransactionORM(id=str(uuid4()), **tx.dict())
    db.add(new_tx)
    db.commit()
    db.refresh(new_tx)
    return new_tx

@app.put("/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(tx_id: str, tx: TransactionCreate, db: Session = Depends(get_db)):
    existing_tx = db.query(TransactionORM).filter(TransactionORM.id == tx_id).first()
    if not existing_tx:
        return {"error": "Transaction not found"}

    for key, value in tx.dict().items():
        setattr(existing_tx, key, value)
    db.commit()
    db.refresh(existing_tx)
    return existing_tx

@app.delete("/transactions/{tx_id}")
def delete_transaction(tx_id: str, db: Session = Depends(get_db)):
    tx = db.query(TransactionORM).filter(TransactionORM.id == tx_id).first()
    if not tx:
        return {"error": "Transaction not found"}

    db.delete(tx)
    db.commit()
    return {"message": "Transaction deleted"}

@app.get("/summary/totals")
def summary_totals(days: int = 0, db: Session = Depends(get_db)):
    query = db.query(TransactionORM)
    if days:
        cutoff = date.today() - timedelta(days=days)
        query = query.filter(TransactionORM.date >= cutoff)
    results = query.with_entities(TransactionORM.type, TransactionORM.amount).all()
    return {
        "income": sum(amount for t_type, amount in results if t_type == "income"),
        "expense": sum(amount for t_type, amount in results if t_type == "expense"),
    }

@app.get("/categories-summary")
def categories_summary(days: int = 0, db: Session = Depends(get_db)):
    query = db.query(TransactionORM)
    if days:
        cutoff = date.today() - timedelta(days=days)
        query = query.filter(TransactionORM.date >= cutoff)

    transactions = query.all()
    income = {}
    expense = {}
    for tx in transactions:
        target = income if tx.type == "income" else expense
        target[tx.category] = target.get(tx.category, 0) + tx.amount
    return {
        "income": [{"category": k, "total": v} for k, v in income.items()],
        "expense": [{"category": k, "total": v} for k, v in expense.items()],
    }